# Testbericht V-024 — unabhängiger Test-Agent

Bericht des konfigurierten Test-Agenten (`test-agent`) für das Arbeitspaket
V-024. Es wurden ausschließlich Testdateien geschrieben bzw. geändert; keine
Produktionsdateien, kein Commit, kein Staging, kein Branchwechsel.

## Geänderte Testdateien

- `tests/unit/test_install_lifecycle.py` (Klasse `RunningGuardTest`)
- `tests/unit/test_run_control.py` (neue Klasse `RunsCommandTest`)

## Testfälle

### `RunningGuardTest` (`tests/unit/test_install_lifecycle.py`)

| Test | Vorbedingung | Aktion | Erwartung | Akzeptanzkriterium |
|---|---|---|---|---|
| `test_update_proceeds_when_a_running_record_has_no_session` | Installiertes Toolchain-Abbild, `runs.json` mit `state=running`, `session=vibe-lauf-weg`, Fake-tmux meldet Sitzung als fehlend | `--yes --update` | Exit 0, Programmdateien aktualisiert, keine Sperrmeldung | 1 |
| `test_update_proceeds_when_a_starting_record_has_no_session` | dito mit `state=starting` | dito | Exit 0, Programmdateien aktualisiert | 1 |
| `test_update_refuses_while_a_run_is_live` (bestehend, angepasst) | `runs.json` mit `state=running` und `session=vibe-lauf-1`, Fake-tmux meldet Sitzung als existierend | `--yes --update` | Exit 1, „wird gerade verwendet“, `lauf-1`, Datei bleibt `ALT` | 2 |
| `test_update_refuses_while_a_starting_run_is_live` (neu) | dito mit `state=starting` | dito | Exit 1, Sperre | 2 |
| `test_update_refuses_conservatively_when_tmux_is_unavailable` (neu) | Live-Eintrag, `which("tmux")` liefert `None` | `--yes --update` | Exit 1, konservative Sperre | 3 |
| `test_update_refuses_when_the_run_state_is_unreadable` (bestehend, unverändert) | defektes `runs.json` | `--yes --update` | Exit 1, „nicht lesbar“ | 3 |

Der bestehende Live-Test wurde nicht abgeschwächt: Er prüft weiter Exit 1,
Sperrtext, Lauf-ID und unveränderte Programmdatei, jetzt zusätzlich mit
nachgebildeter existierender tmux-Sitzung.

### `RunsCommandTest` (`tests/unit/test_run_control.py`)

| Test | Vorbedingung | Aktion | Erwartung | Akzeptanzkriterium |
|---|---|---|---|---|
| `test_runs_list_shows_state_session_status_and_project_path_without_changes` | Drei Einträge (live, verwaist inkl. fehlendem Projektpfad, finished); Fake-tmux kennt nur die Live-Sitzung | `vibe runs list` | Exit 0; ID, Zustand und Projektpfad je Zeile; verwaiste Zeile enthält „verwaist“, Live-Zeile nicht; `runs.json` byte-identisch | 4 |
| `test_runs_without_argument_lists_entries_too` | Ein verwaister Eintrag | `vibe runs` | Exit 0; Eintrag mit „verwaist“ sichtbar; Register unverändert | 4 |
| `test_prune_marks_only_orphaned_live_records_ended` | `running`/`starting` ohne Sitzung, `running` mit Sitzung, `finished`, `stopped`, `ended`; Fake-tmux kennt nur die Live-Sitzung | `vibe runs prune` | Verwaiste `starting`/`running` → `ended`; alle anderen Einträge vollständig unverändert; kein `kill-session` | 5 |
| `test_prune_works_when_the_project_directory_is_gone` | Eintrag zeigt auf nicht existierendes Projektverzeichnis, Sitzung fehlt | `vibe runs prune` | Exit 0; Zustand → `ended`; kein `kill-session` | 5 |
| `test_prune_reports_records_without_a_session_and_keeps_them` | `running`-Eintrag ohne Sitzungsangabe | `vibe runs prune` | Eintrag vollständig unverändert; Zeile nennt ihn und enthält „Sitzung“; kein `kill-session` | 6 |

Die `vibe runs`-Tests laufen über einen echten CLI-Subprozess mit einer
gefälschten `tmux`-Datei im temporären `PATH` (nur `has-session` und
`kill-session`, alle Aufrufe werden protokolliert). Es werden keine echten
Sitzungen, Prozesse oder produktiven `VIBE`-/HOME-Pfade verwendet.

## Rotphase vor der Implementierung

```
python3 -m unittest discover -s tests/unit -p 'test_install_lifecycle.py' -v
→ Ran 42 tests, FAILED (failures=2), Exit 1

FAIL: test_update_proceeds_when_a_running_record_has_no_session
  AssertionError: 1 != 0 : ... FEHLER: Die Installation wird gerade verwendet ...
  - Agentenlauf lauf-weg ist running
FAIL: test_update_proceeds_when_a_starting_record_has_no_session
  AssertionError: 1 != 0 : ... Agentenlauf lauf-start-weg ist starting
```

Erwarteter Grund: Die damalige Sperre blockierte allein anhand des Zustands und
prüfte die Sitzung nicht.

```
python3 -m unittest discover -s tests/unit -p 'test_run_control.py' -v
→ Ran 28 tests, FAILED (failures=5), Exit 1

FAIL: test_prune_marks_only_orphaned_live_records_ended
FAIL: test_prune_reports_records_without_a_session_and_keeps_them
FAIL: test_prune_works_when_the_project_directory_is_gone
FAIL: test_runs_list_shows_state_session_status_and_project_path_without_changes
FAIL: test_runs_without_argument_lists_entries_too
```

Erwarteter Grund: `vibe runs` war noch nicht im Dispatch vorhanden; die
Ausgabe war die Hilfe, und `runs.json` blieb unverändert.

## Nachbesserung des Testaufbaus

Nach der Implementierung meldeten zwei der neuen Positivtests Exit 2, weil ihr
Fake-`which` nur für `tmux` einen Pfad lieferte und das Setup deshalb die
Pflichtwerkzeuge git/flock/curl/opencode als fehlend ansah. Der Test-Agent
korrigierte ausschließlich den Testaufbau: `which` liefert jetzt für jedes
Werkzeug einen Pfad; die tmux-Sitzungsprüfung bleibt über den injizierten
`runner` gesteuert. Die fachlichen Assertions blieben unverändert.

## Grünphase nach der Implementierung

```
python3 -m unittest discover -s tests/unit -p 'test_install_lifecycle.py' -v
→ Ran 42 tests, OK, Exit 0

python3 -m unittest discover -s tests/unit -p 'test_run_control.py' -v
→ Ran 28 tests, OK, Exit 0
```

Die Guard-Gegenfälle (existierende Sitzung, fehlendes tmux, unlesbares
Register) sowie `runs list`/`runs prune` bleiben streng und grün.

## Nachtrag Reviewrunde 1

Der Reviewer beanstandete, dass `list`/`prune` eine nicht prüfbare
tmux-Abfrage wie eine fehlende Sitzung behandelten. Der Test-Agent ergänzte
daraufhin in `RunsCommandTest`:

- `test_runs_list_marks_an_unverifiable_session_not_as_orphaned` —
  Fake-tmux antwortet mit Exit 2; die Zeile muss „nicht prüfbar“ und darf
  nicht „verwaist“ enthalten; das Register bleibt byte-identisch.
- `test_prune_keeps_unverifiable_records_and_reports_them` — der Record
  bleibt vollständig unverändert, die Ausgabe nennt „nicht prüfbar“, die
  Zusammenfassung zählt ihn, und es gibt kein `kill-session`.

Rotphase am damaligen Stand:

```
python3 -m unittest discover -s tests/unit -p 'test_run_control.py' -v
→ Ran 30 tests, FAILED (failures=2), Exit 1
   FAIL: test_prune_keeps_unverifiable_records_and_reports_them
   FAIL: test_runs_list_marks_an_unverifiable_session_not_as_orphaned
```

Zusätzlich ergänzte der Test-Agent die Regressionssicherung
`test_force_bypasses_the_guard_of_a_live_session` in `RunningGuardTest`
(existierende Sitzung: ohne `--force` Sperre, mit `--force` Durchlassen).

Grünphase nach der Anpassung:

```
python3 -m unittest discover -s tests/unit -p 'test_run_control.py' -v
→ Ran 30 tests, OK, Exit 0

python3 -m unittest discover -s tests/unit -p 'test_install_lifecycle.py' -v
→ Ran 43 tests, OK, Exit 0
```
