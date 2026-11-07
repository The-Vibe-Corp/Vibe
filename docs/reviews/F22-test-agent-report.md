# F22 — Bericht des unabhängigen Test-Agenten

Arbeitspaket: F22 „Preflight nicht bestanden“
Branch: `feature/f22-preflight-rueckfragen`
Testbefehl: `python3 -m unittest discover -s tests/unit -p 'test_f22_preflight_assist.py' -v`

## Herkunft

Die Tests wurden vom konfigurierten Test-Agenten (`test-agent`) vor der
Implementierung aus dem Arbeitspaket und `SPEC.md` abgeleitet, geschrieben und
ausgeführt. Der Test-Agent hat keine Produktionsdateien geändert.

## Testfälle

| # | Testname | Vorbedingung | Aktion | Erwartetes Ergebnis |
| --- | --- | --- | --- | --- |
| 1 | `test_direct_runner_without_assist_aborts_without_question` | Unsauberer Arbeitsbaum | Erst mit `VIBE_PREFLIGHT_ASSIST=1`, dann ohne starten | Mit Assistenz Rückfrage; ohne Variable Exit 2, keine neue Rückfrage, kein Agentenaufruf |
| 2 | `test_vibe_run_starts_runner_with_preflight_assist` | `bin/vibe` mit Attrappen für `run`/tmux | `cmd_run("proj")` | Startbefehl enthält `VIBE_PREFLIGHT_ASSIST=1` |
| 3 | `test_blocked_preflight_asks_with_project_findings_and_exact_options` | Unsauberer Arbeitsbaum | Läufer mit Assistenz starten | Frage nennt Projekt und „Arbeitsbaum“/`unfertig.txt`; Optionen exakt `["Erneut prüfen", "Lauf abbrechen"]`; keine freie Antwort |
| 4 | `test_retry_after_fix_runs_the_first_package` | Unsauberer Arbeitsbaum | Frage abwarten, Datei entfernen, Option 0 | Preflight besteht, F1 wird gestartet und geschlossen; Exit 0 |
| 5 | `test_retry_while_still_blocked_creates_a_new_question` | Befund bleibt | Option 0 | Neue Rückfrage mit neuer ID; kein Agentenaufruf; danach Option 1 → Exit 2 |
| 6 | `test_multiple_findings_are_asked_one_after_another` | Unsauberer Arbeitsbaum und fehlender Reviewer | Erste Frage 0, Reviewer anlegen, zweite Frage 0 | Erst Arbeitsbaum, dann REVIEWER als eigene Frage; danach F1 erfolgreich |
| 7 | `test_abort_ends_with_exit_2_marks_run_blocked_and_answers_question` | Lauf-ID, unsauberer Arbeitsbaum | Option 1 | Exit 2, kein Agentenaufruf, Antwortdatei vorhanden, Laufregister `blocked`/Exit 2 |
| 8 | `test_timeout_ends_run_with_exit_2_keeps_question_open_and_names_its_id` | `VIBE_PREFLIGHT_QUESTION_TIMEOUT=2`, keine Antwort | Läufer warten lassen | Exit 2, kein Agentenaufruf, Frage offen, Abbruchgrund enthält Frage-ID |
| 9 | `test_autonomous_mode_prevents_a_question` | Positivkontrolle, danach `autonomous.json` aktiv | Zweiter Lauf mit Assistenz | Keine neue Rückfrage; Exit 2; kein Agentenaufruf |
| 10 | `test_enabling_autonomous_during_wait_ends_immediately` | Laufende Rückfrage, Timeout 120 s | Autonomen Modus während des Wartens einschalten | Warten endet sofort (< 15 s), Exit 2, kein Agentenaufruf, Frage offen |
| 11 | `test_successful_preflight_creates_no_question` | Positivkontrolle, danach sauberes Projekt | Sauberen Lauf mit Assistenz starten | Keine neue Rückfrage; F1 läuft; Exit 0 |

## Beobachtete Rotphase

Vor der Implementierung:

```
python3 -m unittest discover -s tests/unit -p 'test_f22_preflight_assist.py' -v
```

Exit-Code 1, `Ran 11 tests`, `FAILED (failures=11)`.

- Zehn Tests scheiterten mit
  `AssertionError: Läufer endete ohne erwartete Rückfrage (Exit 2): BLOCKIERT: Arbeitsbaum ist nicht leer: ?? unfertig.txt / ABBRUCH: Preflight nicht bestanden. Es wurde kein Arbeitspaket gestartet.`
- `test_vibe_run_starts_runner_with_preflight_assist` scheiterte mit
  `AssertionError: 'VIBE_PREFLIGHT_ASSIST=1' not found in 'tmux new-session ...'`.

## Geänderte Testdateien

- Neu: `tests/unit/test_f22_preflight_assist.py`
- Angepasst: `tests/unit/runner_support.py` (kopiert zusätzlich
  `vibe_questions.py`, `vibe_autonomous.py`, `vibe_storage.py` in die
  Testinstallation)
- Keine Produktionsdateien geändert.
