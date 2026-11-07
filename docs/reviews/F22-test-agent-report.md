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

## Nacharbeit nach Review-Runde 1

Der Reviewer meldete zwei Minor-Befunde zu unlesbaren Antworten und nicht
angebotenen Optionen. Der Test-Agent ergänzte daraufhin zwei Tests in
`tests/unit/test_f22_preflight_assist.py`:

- `test_corrupt_answer_ends_with_clear_error` — eine absichtlich unlesbare
  `.answer.json` führt zu Exit 2, ohne Traceback, mit Rückfrage-ID und
  „nicht lesbar“ in der Ausgabe.
- `test_invalid_option_ends_with_clear_error` — eine gültige Antwortdatei mit
  `option: 2` führt zu Exit 2, ohne Agentenaufruf und ohne stillschweigende
  Wiederholung; die Ausgabe nennt die Rückfrage-ID und „ungültige Antwort“.

Beobachtete Rotphase vor der Produktionsanpassung: Exit 1, 13 Tests, 11
bestanden, 2 fehlgeschlagen. Der erste Test zeigte einen Python-Traceback
(`ValueError: Antwort nicht lesbar: ...`), der zweite startete trotz
ungültiger Option das Arbeitspaket F1 und endete mit Exit 0.

Nach der Produktionsanpassung: 13 Tests OK.

## Nacharbeit: Freitext als Anweisung an den Agenten

Der Nutzer meldete, dass die Rückfrage zwar erscheint, aber keine Lösung
erlaubt. Der Test-Agent ergänzte daraufhin sechs Tests und erweiterte die
Agenten-Attrappe:

- `test_free_text_answer_is_explained_as_agent_instruction` — `free_text` ist
  `True`, die Optionen bleiben exakt `["Erneut prüfen", "Lauf abbrechen"]`, der
  Fragetext erklärt die Agentenanweisung.
- `test_text_answer_runs_agent_in_project_then_starts_package` — eine
  Freitextantwort startet den Agenten im Projektordner; der Prompt enthält
  Anweisung und Befunde; danach läuft F1 und der Lauf endet mit Exit 0.
- `test_text_wins_over_a_selected_option` — Freitext hat Vorrang vor Option 0.
- `test_failed_agent_run_ends_with_exit_2_and_no_package` — Agenten-Exit 1
  beendet den Lauf mit Exit 2, ohne Arbeitspaket; Register `blocked`.
- `test_empty_text_with_option_0_retries_without_agent` — ohne Text bleibt
  Option 0 eine reine erneute Prüfung.
- `test_ten_agent_rounds_then_exit_2` — nach zehn Agentenrunden endet die
  Assistenz mit Exit 2.

Die Attrappe in `tests/unit/runner_support.py` erkennt Preflight-Aufträge und
protokolliert sie separat; `FAKE_PREFLIGHT_MODE` steuert `fix`, `fail` und
`noop`.

Beobachtete Rotphase vor der Produktionsanpassung: Exit 1, 19 Tests, 6
fehlgeschlagen (u. a. `False is not True` bei `free_text`, `0 != 1` bei den
Preflight-Aufrufen und „Ungültige Antwort … (Option None)“). Nach der
Produktionsanpassung: 19 Tests OK.

Die vollständige Unit-Suite zeigte in der Rotphase 1048 Tests mit 7 Fehlern:
sechs erwartete F22-Fehler und der vorbestehende, unabhängige Fehler
`test_dry_run_explains_pi_and_its_install_command`.

