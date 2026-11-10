# B9 — Testbericht des Test-Agenten

Datum: 2026-11-10
Repository: `/run/host/var/mnt/data/Dokumente/Informatik/VibeCode/vibe`
Branch: `feature/b9-selbstreparatur`
Ausgangsstand: `a18587e`
Umsetzung/Tests: `bb94d86`
Ticket: B9 „Blockierte Pakete selbst beheben und Reparatur anbieten“
(`FEEDBACK.md`, letzter B9-Block), Kriterien zusätzlich aus `SPEC.md`
(Abschnitt „Qualität und Abnahme“) und `AGENTS.md`.

## 0. Herkunft und Umfang dieses Berichts

Die B9-Tests wurden vom Test-Agenten vor der Implementierung aus dem Ticket
und `SPEC.md` abgeleitet, nicht aus dem Implementierungsdiff. Der
Rotphasenlauf ist beobachtet und in Abschnitt 4 mit den tatsächlichen
Ergebniszeilen dokumentiert. Die B9-Suite liegt in
`tests/unit/test_b9_self_repair.py` (12 Tests) und wurde mit der Umsetzung in
`bb94d86` versioniert. Zusätzlich wurden zwei bestehende F22-Tests und zwei
bestehende Läufertests an das im Ticket verlangte Verhalten angepasst
(Abschnitte 3.2, 3.3 und 6).

In der aktuellen Sitzung habe ich ausschließlich diesen Bericht neu angelegt.
Ich habe keine Produktionsdatei, keine Konfiguration und keinen Test
geändert; die in Abschnitt 5 genannten Befehle habe ich zur Bestätigung
erneut ausgeführt.

## 1. Ableitung aus Ticket und SPEC

Aus dem B9-Block in `FEEDBACK.md` ergeben sich fünf prüfbare
Akzeptanzkriterien:

* **AK1 — Mehrfachnachweis:** Eine Nachweiszeile mit mehreren Commits gilt
  als belegt, sobald mindestens ein gelisteter Commit auf dem Paketbranch
  liegt und mit `<ID>:` beginnt. Liegt keiner dort, bleibt die Schranke
  blockiert und nennt die geprüften Commits.
* **AK2 — Drei Optionen:** Die F16-Preflight-Rückfrage bietet
  `Erneut prüfen` (0), `Lauf abbrechen` (1) und `Agent behebt die Befunde`
  (2) in fester Reihenfolge. Option 2 startet den Agenten mit einer aus den
  Befunden abgeleiteten Anweisung; Freitext hat Vorrang.
* **AK3 — Reparaturrunden:** Ein Pakettest- oder Schrankenbefund wird im
  selben Arbeitsbaum höchstens zwei Runden repariert. Eine erfolgreiche
  Reparatur führt zum Merge; ein dauerhafter Befund blockiert nach genau
  zwei Reparaturrunden ohne Merge und ohne neues Paket.
* **AK4 — Keine fremden Änderungen:** Reparaturaufträge bearbeiten nur das
  aktuelle Paket, verwerfen keine fremden Änderungen und schwächen die
  Abnahme nicht ab. Der Test prüft dies über den unveränderten
  Basis-Commit, den fehlenden Merge und das Fehlen eines F2-Auftrags.
* **AK5 — Unsauberer Integrationsstand:** Am Laufende ist ein unsauberer
  Stand mit Assistenz über denselben Pfad behebbar; ohne Assistenz oder
  nach Abbruch bleibt es beim Blockieren.

`SPEC.md` („Qualität und Abnahme“) verlangt zusätzlich temporäre
HOME-/VIBE-Verzeichnisse, keine Tests gegen produktive Konfigurationen,
keine echten kostenpflichtigen Modellaufrufe und Testprotokolle mit Befehl,
Ergebnis und Grenzen. Die Suiten arbeiten ausschließlich in temporären
Verzeichnissen; Modell- und Netzaufrufe sind durch Attrappen ersetzt
(Abschnitt 7).

## 2. Testdateien

| Datei | Testfälle | Stand |
|---|---|---|
| `tests/unit/test_b9_self_repair.py` | 12 | neu, vom Test-Agenten |
| `tests/unit/test_f22_preflight_assist.py` | 19 | zwei Tests an drei Optionen angepasst |
| `tests/unit/test_runner_package_gates.py` | 12 | zwei Tests an Reparaturrunden angepasst |

## 3. Testfälle

### 3.1 `tests/unit/test_b9_self_repair.py` (12 Tests)

Gemeinsame Vorbedingung: temporäre Wurzel mit eigenem `home`, `state`,
`runtime`, `install` und Projekt; `VIBE`, `HOME`, `VIBE_STATE`,
`VIBE_RUNTIME`, `VIBE_INSTALL`, `VIBE_AGENTS_DIR`, `XDG_CONFIG_HOME` und
`VIBE_STORAGE_LOCK_DIR` zeigen in die temporäre Wurzel; Agenten-, `curl`-
und `vibe`-Attrappen liegen in einem eigenen `PATH`. Die Läuferklassen
verwenden echtes Git und eine nachgebildete opencode-Ablage; die
Schrankenklasse arbeitet mit echten Mini-Repositories. Es werden keine
Modelle, Router oder externen Dienste aufgerufen.

| # | Testname | Kriterium | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|---|
| 1 | `PackageGateTest.test_gate_accepts_proof_when_one_of_several_commits_is_on_the_branch` | AK1 | Echtes Mini-Repo; F1-Umsetzungs- und Test-Commit liegen auf `main`; die Nachweiszeile nennt zuerst den Basiscommit (außerhalb des Paketbranches) und danach den F1-Test-Commit; Doku und Review sind vorhanden. | `gate_errors(project, "F1", base)`. | Leere Fehlerliste. Der erste gelistete Commit allein hätte die Schranke blockiert; der zweite, paketpräfixierte Commit genügt. |
| 2 | `PackageGateTest.test_gate_blocks_and_names_all_checked_commits_when_none_is_on_the_branch` | AK1 | Zwei fremde Commits auf Branch `other`; auf `main` liegt nur der F1-Commit; die Nachweiszeile nennt beide fremden Hashes; Doku und Review sind vorhanden. | `gate_errors(project, "F1", base)`. | Nichtleere Fehlerliste; beide geprüften Hashes kommen im Fehlertext vor. |
| 3 | `PreflightAssistOptionsTest.test_assist_offers_three_options_and_option_two_returns_agent_action` | AK2 | Isoliertes Projekt mit `unfertig.txt`; `assist_preflight` läuft in einem Thread und legt eine echte F16-Rückfrage an. | Rückfrage abwarten, Optionen prüfen, mit Option 2 antworten, Thread joinen. | Optionen exakt `["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"]`; `action == "agent"`; nichtleere Anweisung mit `Arbeitsbaum` und `unfertig.txt`. |
| 4 | `PreflightAssistOptionsTest.test_free_text_wins_over_option_two` | AK2 | Wie Fall 3. | Mit Option 2 und dem Freitext „Bitte nur die Notizen prüfen, nichts committen“ antworten. | `action == "agent"`; `instruction` entspricht exakt dem Freitext — der Freitext verdrängt die abgeleitete Befund-Anweisung. |
| 5 | `PreflightAssistOptionsTest.test_option_zero_retries_and_option_one_aborts` | AK2 | Wie Fall 3. | Zuerst Option 0; eine neue Rückfrage mit anderer ID abwarten; dann Option 1. | Beide Rückfragen bieten die drei Optionen; die zweite hat eine andere ID; `action == "abort"`; kein Agentenauftrag. |
| 6 | `RunnerPreflightOptionTest.test_preflight_option_two_runs_the_agent_in_the_project` | AK2 | Isolierter Läufer mit echtem Git und Attrappen; Projekt mit `unfertig.txt`; `VIBE_PREFLIGHT_ASSIST=1`; `B9_MODE=fix-integration`. | Läufer starten, Rückfrage abwarten, Option 2 antworten. | Exit 0; Aufrufe genau `["repair", "package"]`; `cwd` der Reparatur ist der Projektordner; Prompt nennt `Arbeitsbaum` und `unfertig.txt`; die Datei ist entfernt; Bericht enthält `Geschlossen: F1`. |
| 7 | `RunnerPackageRepairTest.test_gate_finding_is_repaired_in_the_same_worktree_and_merged` | AK3 | Projekt mit einem Paket; `B9_MODE=fix-gate` lässt zunächst Doku/Review fehlen und ergänzt sie in der Reparatur; `VIBE_MAX_PACKAGES=1`. | Läufer ausführen. | Exit 0; Aufrufe `["package", "repair"]`; beide im selben realpath; Reparaturprompt nennt `docs/features/F1.md`; HEAD ist verändert und `impl-F1.txt` liegt in HEAD; `Geschlossen: F1`; keine Arbeitskopie bleibt liegen. |
| 8 | `RunnerPackageRepairTest.test_package_test_finding_is_repaired_in_the_same_worktree_and_merged` | AK3 | `VERIFY_PACKAGE` schlägt fehl, solange `package_test_fail.txt` existiert; `B9_MODE=fix-tests` behebt den Befund in der Reparatur; `VIBE_MAX_PACKAGES=1`. | Läufer ausführen. | Exit 0; Aufrufe `["package", "repair"]` im selben realpath; Reparaturprompt nennt F1 und einen Pakettest-Begriff (`pakettest`, `paketprüfung`, `package_test_fail` oder `nicht grün`); die Datei ist nach dem Merge nicht mehr im Projekt; `Geschlossen: F1`. |
| 9 | `RunnerPackageRepairTest.test_persistent_gate_finding_blocks_after_two_repairs_without_merge` | AK3, AK4 | Zwei Pakete; `B9_MODE=persist-gate` lässt Doku/Review dauerhaft fehlen; `VIBE_MAX_PACKAGES=2`. | Läufer ausführen. | Exit 1; Aufrufe genau `["package", "repair", "repair"]`; alle im selben realpath; beide Reparaturprompts nennen `docs/features/F1.md`; HEAD unverändert; `cat-file -e HEAD:impl-F1.txt` liefert einen Nicht-Null-Status; kein `Geschlossen: F1`; kein Prompt für F2; Ausgabe enthält `BLOCKIERT` und den Befund. |
| 10 | `RunnerIntegrationAssistTest.test_dirty_integration_is_repaired_with_assistance_and_final_check_runs` | AK5 | Projekt mit `unfertig.txt`; `VERIFY_FULL` schreibt einen Marker; `VIBE_KEEP_CHANGES=1`, Assistenz aktiv, `VIBE_MAX_PACKAGES=1`, `B9_MODE=fix-integration`. | Läufer starten, Rückfrage abwarten, Option 2 antworten. | Exit 0; Aufrufe `["package", "repair"]`; Reparatur läuft im Projektordner; Prompt nennt `unfertig.txt` und einen Integrationsbegriff; die Datei ist entfernt; der Marker existiert; `git status --porcelain` ist leer. |
| 11 | `RunnerIntegrationAssistTest.test_dirty_integration_abort_keeps_the_block` | AK5 | Wie Fall 10. | Auf die Rückfrage mit Option 1 antworten. | Exit 1; Aufrufe nur `["package"]`; kein Marker; Ausgabe enthält `Integrationsstand ist nicht sauber`; `unfertig.txt` bleibt erhalten. |
| 12 | `RunnerIntegrationAssistTest.test_dirty_integration_without_assistance_keeps_the_block` | AK5 | Wie Fall 10, aber ohne `VIBE_PREFLIGHT_ASSIST`. | Läufer ausführen. | Exit 1; Aufrufe nur `["package"]`; keine Rückfrage; kein Marker; Ausgabe enthält `Integrationsstand ist nicht sauber`. Dieser Fall ist der unveränderte Basisanker. |

Fehlerfälle: Die Schrankenfälle prüfen die blockierte Variante ausdrücklich
(Fall 2 und 9). Die Assistenzfälle prüfen Abbruch (Fall 5, 11) und fehlende
Assistenz (Fall 12). Ein unerwarteter Merge, eine fremde Arbeitskopie, ein
F2-Auftrag oder eine fehlende Abschlussprüfung lassen die jeweilige Assertion
fehlschlagen.

### 3.2 Angepasste F22-Tests (2)

| # | Testname | Kriterium | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|---|
| 1 | `QuestionContentTest.test_blocked_preflight_asks_with_project_findings_and_exact_options` | AK2 | Projekt mit `unfertig.txt`; `VIBE_PREFLIGHT_ASSIST=1`, Frage-Timeout 30 s. | Rückfrage abwarten; danach Option 1 antworten. | Projektname enthält `proj`; Text nennt `Arbeitsbaum` und `unfertig.txt`; Optionen exakt die drei B9-Optionen; `free_text` ist wahr; Exit 2 nach Abbruch. |
| 2 | `QuestionContentTest.test_free_text_answer_is_explained_as_agent_instruction` | AK2 | Projekt mit unfertigem Arbeitsbaum; Assistenz aktiv. | Rückfrage abwarten; danach Option 1 antworten. | `free_text` ist wahr; Optionen exakt die drei B9-Optionen; Text enthält `Anweisung` und `Agent`; Exit 2 nach Abbruch. |

Der zusätzliche Test `InvalidAnswerTest.test_invalid_option_ends_with_clear_error`
wurde nicht in seiner Aussage geändert, sondern musste die nicht mehr
gültige Optionsnummer anpassen: Er antwortet jetzt mit `3` statt `2`, weil `2`
seit B9 eine gültige Option ist. Seine Assertions (Exit 2, kein Agentenlauf,
ID im Fehlertext, nur eine Rückfrage) sind unverändert.

### 3.3 Angepasste Läufertests (2)

| # | Testname | Kriterium | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|---|
| 1 | `ClosingGateTest.test_missing_artifacts_block_and_stop_the_run` | AK3 | Projekt mit F1; `FAKE_MODE=no-artifacts`, sodass die Abschlussschranke fehlt. | Läufer ausführen. | Exit 1; Meldung `Abschlussschranke für F1`; genau drei Agentenaufrufe (Erstlauf plus zwei Reparaturrunden), alle im selben Arbeitsbaum; die blockierte Arbeitskopie bleibt zur Diagnose liegen; Ausgabe enthält `BLOCKIERT`. |
| 2 | `ReportTest.test_report_lists_closed_blocked_and_open_packages` | AK3 | Drei Pakete F1/F2/F3; Sequenz `complete,no-artifacts,no-artifacts,no-artifacts`; `VIBE_MAX_PACKAGES=3`. | Läufer ausführen. | Exit 1; Bericht nennt `Geschlossen: F1`, `Blockiert: F2`, `Offen: F3`; `proj.report.txt` existiert. F2 scheitert im Erstlauf und in beiden Reparaturrunden; der letzte Sequenzeintrag wiederholt sich. |

## 4. Rotphase vor der Implementierung

Die folgenden Läufe wurden im Rotphasenlauf dieses Arbeitspakets vor der
Implementierung beobachtet. Da die Implementierung inzwischen vorliegt, habe
ich sie in der aktuellen Sitzung nicht erneut ausgeführt; die Ergebniszeilen
stammen aus den damaligen Protokollen
(`/tmp/opencode/b9-red-report.log`, `/tmp/opencode/f22-red-report.log`).

### 4.1 B9-Suite

```
python3 -m unittest tests.unit.test_b9_self_repair -v
```

```
Ran 12 tests in 4.092s

FAILED (failures=10, errors=1)
```

Exit-Code: 1.

Zehn Failures und ein Error an den geplanten neuen Schnittstellen:

* Failures: `test_gate_accepts_proof_when_one_of_several_commits_is_on_the_branch`,
  `test_gate_blocks_and_names_all_checked_commits_when_none_is_on_the_branch`,
  `test_assist_offers_three_options_and_option_two_returns_agent_action`,
  `test_option_zero_retries_and_option_one_aborts`,
  `test_preflight_option_two_runs_the_agent_in_the_project`,
  `test_gate_finding_is_repaired_in_the_same_worktree_and_merged`,
  `test_package_test_finding_is_repaired_in_the_same_worktree_and_merged`,
  `test_persistent_gate_finding_blocks_after_two_repairs_without_merge`,
  `test_dirty_integration_is_repaired_with_assistance_and_final_check_runs`,
  `test_dirty_integration_abort_keeps_the_block`.
* Error: `test_free_text_wins_over_option_two` — Option 2 war noch nicht
  angeboten, `vibe_questions.answer` wies die Auswahl als außerhalb der
  Möglichkeiten zurück.

Der elfte Test `test_dirty_integration_without_assistance_keeps_the_block`
war grün. Er prüft das unveränderte Bestandsverhalten (Blockade ohne
Assistenz) und dient als Basisanker: Die Suite scheiterte an den neuen
Schnittstellen, nicht an einer defekten Umgebung.

### 4.2 F22-Suite

```
python3 -m unittest tests.unit.test_f22_preflight_assist -v
```

```
Ran 19 tests in 17.026s

FAILED (failures=2)
```

Exit-Code: 1. Die beiden Failures sind genau die auf drei Optionen
erweiterten Prüfungen:

* `QuestionContentTest.test_blocked_preflight_asks_with_project_findings_and_exact_options`
* `QuestionContentTest.test_free_text_answer_is_explained_as_agent_instruction`

Beide scheiterten mit der Differenz
`['Erneut prüfen', 'Lauf abbrechen']` gegen
`['Erneut prüfen', 'Lauf abbrechen', 'Agent behebt die Befunde']`.

### 4.3 Kontextsuiten im Rotphasenlauf

Die Kontextsuiten `test_package_gates` (33 Tests) und
`test_runner_package_gates` (12 Tests) liefen im Rotphasenlauf mit
**45 Tests OK**. Dieser Lauf stammt aus der Rotphase; ein separates Log
liegt in `/tmp/opencode` nicht vor, und ich habe ihn in der aktuellen
Sitzung nicht erneut ausgeführt. Er belegt, dass die Bestandssuiten vor der
Implementierung grün waren und die beobachteten Fehlschläge aus den neuen
Erwartungen stammen.

## 5. Grünphase nach der Implementierung

Alle folgenden Befehle habe ich in der aktuellen Sitzung im Repository
erneut ausgeführt. Python 3.14.8, Git 2.56.0.

### 5.1 B9-Suite

```
python3 -m unittest tests.unit.test_b9_self_repair -v
```

```
Ran 12 tests in 6.897s

OK
```

Exit-Code: 0. Alle 12 Tests `ok`.

### 5.2 Läufer-Suite

```
python3 -m unittest tests.unit.test_runner_package_gates -v
```

```
Ran 12 tests in 7.482s

OK
```

Exit-Code: 0. Alle 12 Tests `ok`, einschließlich der beiden angepassten
Fälle.

### 5.3 F22/F27/Paketschranken

```
python3 -m unittest tests.unit.test_f22_preflight_assist tests.unit.test_f27_keep_changes tests.unit.test_package_gates -v
```

```
Ran 66 tests in 20.923s

OK
```

Exit-Code: 0. Die 66 setzen sich aus 19 F22-, 14 F27- und 33
Paketschranken-Tests zusammen.

### 5.4 Gesamtlauf der sieben relevanten Suiten

```
python3 -m unittest tests.unit.test_b9_self_repair tests.unit.test_runner_package_gates tests.unit.test_f22_preflight_assist tests.unit.test_f27_keep_changes tests.unit.test_package_gates tests.unit.test_gate_already_integrated tests.unit.test_worknotes_sync
```

```
Ran 133 tests in 37.673s

OK
```

Exit-Code: 0. Verteilung: B9 12, Läufer 12, F22 19, F27 14,
Paketschranken 33, `test_gate_already_integrated` 24,
`test_worknotes_sync` 19 — zusammen 133.

## 6. Begründung der Anpassungen bestehender Tests

Keine Assertion wurde in ihrer Aussage abgeschwächt, kein Test wurde
gelöscht, und keine Prüfung wurde durch eine Attrappe ersetzt.

1. **`ClosingGateTest.test_missing_artifacts_block_and_stop_the_run`**
   erwartete vor B9 genau einen Agentenaufruf, weil ein Schrankenbefund den
   Lauf sofort beendete. B9 verlangt bei einem Schrankenbefund bis zu zwei
   Reparaturrunden im selben Arbeitsbaum. Der Test erwartet deshalb jetzt
   den Erstlauf plus zwei Reparaturrunden (drei Aufrufe) und prüft
   zusätzlich, dass alle drei denselben Arbeitsbaum verwenden. Die übrigen
   Aussagen — Exit 1, Schrankenmeldung, zurückbehaltene Arbeitskopie,
   `BLOCKIERT` — bleiben unverändert. Die zusätzliche Prüfung ist strenger,
   nicht schwächer.

2. **`ReportTest.test_report_lists_closed_blocked_and_open_packages`**
   nutzte zuvor die Sequenz `complete,no-artifacts,complete`. Mit B9 löst
   der Befund für F2 zwei Reparaturrunden aus; ein dritter
   `complete`-Eintrag hätte F2 in der Reparatur plötzlich abschließen
   lassen und die erwartete Blockade im Bericht zerstört. Die Sequenz lautet
   jetzt `complete,no-artifacts,no-artifacts,no-artifacts`. Der letzte
   Eintrag wiederholt sich, sodass F2 im Erstlauf und in beiden
   Reparaturrunden weiterhin fehlt. Die Erwartung `Geschlossen: F1`,
   `Blockiert: F2`, `Offen: F3` bleibt wörtlich dieselbe; der Test hält F2
   über die Reparaturrunden hinweg dauerhaft fehlerhaft, statt den
   Reparaturpfad versehentlich erfolgreich zu machen.

3. **`RunnerPackageRepairTest.test_persistent_gate_finding_blocks_after_two_repairs_without_merge`**
   prüft beim fehlenden HEAD-Pfad auf einen Nicht-Null-Status
   (`assertNotEqual(..., 0)`) statt auf exakt `1`. Git 2.56.0 liefert für
   `git cat-file -e HEAD:impl-F1.txt` bei einem fehlenden Pfad `128`; ältere
   Git-Versionen liefern `1`. Die geprüfte Aussage ist „der Pfad ist nicht
   in HEAD vorhanden“; der Nicht-Null-Status bildet genau das
   versionsunabhängig ab. Die Assertion bleibt in ihrer Bedeutung gleich
   streng und wird nicht durch eine schwächere Erwartung ersetzt.

4. **`InvalidAnswerTest.test_invalid_option_ends_with_clear_error`**
   verwendet jetzt die Optionsnummer `3` statt `2`, weil `2` seit B9 eine
   gültige Option ist. Der Test prüft weiterhin dieselbe Aussage: Eine nicht
   angebotene Option wird nicht als „Erneut prüfen“ gedeutet, beendet den
   Lauf mit Exit 2, startet keinen Agenten und lässt genau eine Rückfrage
   bestehen.

## 7. Grenzen

* **Keine Modell- oder Netzaufrufe:** Der Agent, `curl`, `vibe` und die
  opencode-Ablage sind Attrappen. Die Tests belegen die Steuerungslogik des
  Läufers, nicht das Verhalten eines echten Modells oder Providers.
* **Echtes Git:** Die Schrankenfälle und die Läuferfälle arbeiten mit echten
  temporären Git-Repositories und echten Commits. Damit sind Branch-,
  Merge- und `cat-file`-Verhalten real geprüft; nur die Agenten- und
  Dienstschnittstellen sind ersetzt.
* **Rotphase nicht in der aktuellen Sitzung wiederholt:** Die Zahlen in
  Abschnitt 4 stammen aus den Rotphasenprotokollen vor der Implementierung.
  Eine erneute Rotphase wäre nach dem Merge der Umsetzung nicht mehr
  aussagekräftig.
* **Kontextlauf 45 OK:** Der Rotphasen-Kontextlauf der beiden Suiten
  `test_package_gates` und `test_runner_package_gates` ist als damaliges
  Ergebnis überliefert; in der aktuellen Sitzung habe ich ihn nicht erneut
  ausgeführt. Der aktuelle Grünlauf der beiden Suiten ist in Abschnitt 5.2
  und 5.4 belegt.
* **Keine Browser- oder Systemabnahme:** B9 betrifft Läufer-, Schranken- und
  Rückfrageverhalten. Ein Browser- oder Bazzite-/Distrobox-Nachweis ist für
  dieses Arbeitspaket nicht erforderlich und wurde nicht behauptet.
* **Zeitabhängige Wartehilfen:** Die Rückfragefälle pollen mit großzügigen
  Timeouts. Die Attrappen antworten deterministisch; die Tests sind dadurch
  reproduzierbar, messen aber keine reale Antwortlatenz.

## 8. Änderungen durch diesen Bericht

In der aktuellen Sitzung wurde ausschließlich
`docs/reviews/B9-test-agent-report.md` neu angelegt. Kein Produktionscode,
keine Konfiguration, kein Prüfskript und kein Test wurde geändert; es wurde
nichts committet und kein Branch gewechselt.

Die im Bericht dokumentierten Teständerungen stammen aus der Arbeit des
Test-Agenten am Arbeitspaket und sind mit `bb94d86` versioniert:

* `tests/unit/test_b9_self_repair.py` — neu, 12 Tests.
* `tests/unit/test_f22_preflight_assist.py` — zwei Optionsprüfungen auf drei
  Optionen erweitert; ein Invalid-Option-Test auf Index 3 nachgezogen.
* `tests/unit/test_runner_package_gates.py` — zwei Tests an
  Reparaturrunden und die dauerhaft fehlerhafte F2-Sequenz angepasst.
