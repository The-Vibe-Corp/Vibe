# F25 — Herkunftsnachweisbericht des Test-Agenten

Status: Berichtender Nachweis (Test-Agent). Produktionscode wurde von mir
nicht geändert; keine Commits, keine Implementierungsvorschläge umgesetzt.
Quelle der Kriterien: Arbeitspaket F25 (Auftragskontext) und die Forderungen
des Reviewers vom 2026-11-07 (Sessionfortsetzung „einfaches Continue").

## 1. Nachgewiesene Dateien und Rollen

| Pfad | Rolle | Änderung |
|---|---|---|
| `tests/unit/test_f25_session_continue.py` | Testdatei F25 | neu; Stand Ende: 16 Testfälle |
| `tests/unit/runner_support.py` | Testinfrastruktur (Fake) | erweitert, siehe Abschnitt 4 |

Produktionsdateien (`bin/vibe_runs.py`, `bin/vibe-run.sh`, `bin/vibe_packages.py`,
Web-Schicht) wurden vom Test-Agenten nicht berührt. Implementierungscommits:
`b523743` (2026-11-07 23:00:32 +0100, „Sessionfortsetzung bei Wiederholung
(Continue statt Neustart)") und `e96a380` (2026-11-07 23:01:33 +0100,
„Importmanifest minimal halten") — beides durch den Coding-Agenten.

## 2. Rotphase (vor `b523743`/`e96a380`; gleicher Arbeitssession des Test-Agenten)

Exakte Laufbefehle (Arbeitskopie `.../worktrees/vibe-F25-CGiRK6`):

```
python3 -m unittest tests.unit.test_f25_session_continue
python3 -m unittest discover -s tests/unit -v
```

Ergebnis der Rotphase: **7 rot / 6 grün** bei 13 Testfällen. Ergebnis des
vollen Discovery-Laufs vor den Implementierungscommits: 1013 Tests,
14 failures + 65 errors; gegenüber der vorab erhobenen Baselineliste
exakt unverändert bis auf die 7 neuen F25-Rotfälle (Diff-Protokollierung
im Arbeitslog des Test-Agenten, `/tmp/opencode/…-full-scratch.log`).

Die 7 rot gefallenen Fälle mit gekürzten, echten Fehlausgaben:

1. `test_retry_continues_the_captured_session` —
   `AssertionError: '--session' not found in ['run', '--standalone', …]`
   (Zweitversuch lautete komplett ohne `--session`).
2. `test_retry_writes_exactly_one_session_line_per_attempt` —
   `Lists differ: ['[Session] ses_attempt1', '[Session] ses_attempt2'] != []`
   (keine `[Session]`-Zeilen im Laufprotokoll).
3. `test_state_file_holds_the_latest_attempt_session` —
   `AssertionError: 'ses_attempt2' != 'ses_attempt1' : Zustandsdatei hält
   nicht die zuletzt erfasste Session`.
4. `test_stream_last_attempt_session_wins_in_state_file` —
   Erst `'[Session] ses_attempt1' not found in ['Antwort 1']`
   (filterseitige Zeile fehlt), darauf `ses_attempt1` statt `ses_attempt2`
   in der Zustandsdatei.
5. `test_stream_output_stays_free_of_raw_json` —
   `'[Session] ses_attempt1' not found in ['Hallo']`.
6. `test_first_main_session_writes_one_session_line` —
   `'[Session] ses_attempt1' not found in ['Antwort 1']`.
7. `test_second_attempt_session_updates_state_last_wins` —
   `AssertionError: False is not true : Neue Session nicht übernommen`.

Grün in der Rotphase (bewusst als Verankerung des bisherigen Verhaltens):
`test_event_without_main_session_changes_nothing`,
`test_same_session_writes_no_second_session_line`,
`test_subagent_capture_survives_session_sequence`,
`test_retry_without_stream_module_repeats_without_session`,
`test_retry_without_captured_session_repeats_full_prompt`,
`test_quota_failure_makes_no_second_call_and_no_continuation`.

Nach `b523743`+`e96a380`: die 13 ursprünglichen Fälle grün.
`python3 -m unittest tests.unit.test_f25_session_continue` → `Ran 13 tests;
OK` (2026-11-07, nach den Implementierungscommits).

## 3. Testfälle (Kurzfassung; Volltext im Dateikopf der Testdatei)

Übersetzungsstufe — `translate_event` / `stream_events`
(`vibe_runs.py` über `load_module` ohne Installation):
1. `test_first_main_session_writes_one_session_line` — Vor: leerer Zustand;
   Aktion: JSON-Ereignis mit `sessionID` übersetzen; Erwartung: genau eine
   Zeile `[Session] <id>`, Zustand erfasst, `changed=True`.
2. `test_same_session_writes_no_second_session_line` — Vor: Session schon
   erfasst; Aktion: gleiches Ereignis; Erwartung: keine zweite Zeile.
3. `test_second_attempt_session_updates_state_last_wins` — Vor: Zustand
   `ses_attempt1`; Aktion: abweichende `sessionID`; Erwartung: neue
   `[Session] ses_attempt2`-Zeile, Zustand zuletzt („zuletzt gewinnt").
4. `test_event_without_main_session_changes_nothing` — Vor: Zustand
   gesetzt; Aktion: Ereignis ohne `sessionID` und mit leerer `sessionID`;
   Erwartung: keine Zeile, keine Änderung.
5. `test_subagent_capture_survives_session_sequence` — Vor: Ereignisstrom
   mit Haupt- und Subagentensession; Erwartung: F19-Subagentenerfassung
   vollständig, keine Roh-JSON-Ausgabe (Verankerung; grün in Rotphase).
6. `test_stream_last_attempt_session_wins_in_state_file` — Vor:
   Zustandsdatei nach Durchlauf 1; Aktion: zweiter `stream_events`-Lauf mit
   abweichender ID in dieselbe Datei; Erwartung: zweite `[Session]`-Zeile
   und Zustandsdatei = zuletzt erfasste Session.
7. `test_stream_output_stays_free_of_raw_json` — Erwartung: Klartext,
   `[Session]`-Zeile, keine `{`-Zeilen (F19-Garantie).

Läuferintegration — `vibe-run.sh` mit opencode-Attrappe
(`FAKE_ARGS_PATH`-Datensätze, `FAKE_CALLS`, `FAKE_COUNTER`):
8. `test_retry_continues_the_captured_session` — Vor: offenes Paket F25,
   `MAX_RETRIES=1`, Versuchsfolge `fail,complete`; Erwartung: zweiter
   Aufruf enthält `--session ses_attempt1`, beide Prompts enthalten
   „Arbeitspaket F25", Lauf endet „FERTIG". [Rotphase]
9. `test_retry_writes_exactly_one_session_line_per_attempt` — Erwartung:
   exakt je eine `[Session]`-Zeile je Versuch, kein Roh-JSON. [Rotphase]
10. `test_state_file_holds_the_latest_attempt_session` — Erwartung:
    `<log>.state.json` hält `ses_attempt2` nach dem Zweitversuch. [Rotphase]
11. `test_retry_without_stream_module_repeats_without_session` — Vor:
    Installation ohne `vibe_runs.py`; Erwartung: Wiederholung wie bisher,
    kein `--session` (auch nicht leer), vollständiger Prompt, „FERTIG".
12. `test_retry_without_captured_session_repeats_full_prompt` — Vor Suche:
    Attrappe mit `FAKE_OUTPUT` ohne Session-Ereignisse; Erwartung wie 11.
13. `test_quota_failure_makes_no_second_call_and_no_continuation` — Vor:
    `FAKE_MODE=quota`, `MAX_RETRIES=3`; Erwartung: genau ein Aufruf,
    keine „Wiederhole"-Meldung, Exit 1 blockiert.

Review-Abnahme (Forderungen des Reviewers, 2026-11-07):
14. `test_plain_text_session_line_cannot_hijack_the_session` — Vor:
    `FAKE_OUTPUT` liefert je Versuch das JSON-Ereignis der echten
    Hauptsession `ses_attempt1` und darunter die Agentenklartextzeile
    `[Session] ses.bogus/versuch-ohne-ereignis` (Punkt/Schrägstrich).
    Aktion: Läufer mit `fail,complete`. Erwartung (Reviewer): die echte,
    konforme Kennung gewinnt — zweiter Aufruf mit `--session ses_attempt1`;
    Klartextzeile bleibt Protokolltext, landet nicht im Zustand; „FERTIG".
    **Ergebnis: ROT gegen `b523743` — Befund in Abschnitt 5.**
15. `test_third_retry_continues_with_the_latest_captured_session` — Vor:
    `MAX_RETRIES=2` (drei Versuche), Versuchsfolge `fail,fail,complete`;
    Erwartung (tranchiert festgelegt, da das Fake je Aufruf eine neue
    Kennung erzeugt): erster Aufruf ohne `--session`, zweiter mit
    `ses_attempt1`, dritter mit der im Zweitversuch erfassten `ses_attempt2`;
    je Versuch genau eine `[Session]`-Zeile ohne Duplikate; Zustand endet
    `ses_attempt3`; „FERTIG". [GRÜN]
16. `test_agent_plain_session_lines_pass_through_but_do_not_capture`
    (Unit-Ebene zur Naht) — Vor: Ereignis plus Klartextattrappe in einem
    `stream_events`-Durchlauf; Erwartung: Klartextzeile unverändert in der
    Ausgabe, Zustandsdatei hält nur die Ereignis-Session `ses_attempt1`.
    [GRÜN]

## 4. Änderungen in `tests/unit/runner_support.py` (Testinfrastruktur)

1. `FAKE_ARGS_PATH`: je opencode-Aufruf wird die Argumentliste **angehängt**
   statt überschrieben (NUL-getrennt; Datensatzende markiert das Token
   `ARGS_RECORD_END`, das ein Agentenprompt nie enthalten kann, weil
   Argumente kein NUL-Byte tragen können).
2. `FAKE_OPENCODE`: ohne `FAKE_OUTPUT` liefert das Fake je Aufruf genau ein
   JSON-Ereignis `{"type":"text","sessionID":"ses_attempt<counter+1>",…}`
   (Zähler je Aufruf eindeutig). Mit `FAKE_OUTPUT` bleibt das Verhalten
   unverändert, weil `FAKE_OUTPUT` die Ausgabe samt Session selbst vorgibt —
   so bleiben die bestehenden F19-Tests ungestört.
3. Neuer Leser `opencode_arg_records(args_path)`: zerlegt die per Aufruf
   angehängten Datensätze in der Aufrufreihenfolge.

Beweis der Verträglichkeit: voller Discovery-Lauf nach den Änderungen vor
der Implementierung brachte **kein** neues rotes/grünes Ergebnis im Diff
zur Baseline (siehe Abschnitt 2); nach der Implementierung ebenfalls
(Abschnitt 6).

## 5. Offener Befund aus der Review-Abnahme (rot, nicht abgeschwächt)

`test_plain_text_session_line_cannot_hijack_the_session` fällt gegen
`b523743` rot — tatsächliche Ausgabe (gekürzt):

```
AssertionError: Lists differ: ['ses_attempt1'] != []
First list contains 1 additional elements.
First extra element 0: 'ses_attempt1'
```

Das heißt: der Zweitversuch enthält **gar kein** `--session`, obwohl eine
echte, konforme Kennung (`ses_attempt1`) erfasst wurde. Ursache im
Implementierungsstand `b523743` (`bin/vibe-run.sh`, Fehlerbehandlung im
Wiederholungszweig): die Fortsetzungskennung wird aus den `[Session]`-Zeilen
des Protokollanteils des Versuchs gelesen (`sed -n "$((LOG_START_LINE + 1)),
\$p"` → `sed -n 's/^\[Session] //p'` → `tail -n 1`) und dann über eine
Zeichensatzprüfung verworfen. Die Agentenklartextzeile „[Session]
ses.bogus/versuch-ohne-ereignis" steht **nach** der echten
`[Session] ses_attempt1`-Zeile im Protokollanteil, gewinnt als letzte
Zeile (`tail -n 1`), enthält `.` und `/` und verwirft damit die Fortsetzung
komplett. Zwei Konsequenzen desselben Auswahlwegs:

* Konformer Zwangsfall (dieser Test): gültige Fortsetzung geht verloren,
  statt weiterzuführen — gegen das Reviewer-Kriterium „echte, konforme
  Kennung gewinnt, keine Abweichung zu `ses_attempt1`".
* Grenzfall daneben (beobachtbar am selben Codepfad, nicht in diesem Test
  gefordert): eine **zeichensatzkonforme** Klartextzeile des Agenten, die
  als letzte `[Session]`-Zeile steht, würde als Kennung gewinnen — der
  Agentenklartext könnte die Fortsetzungskennung bestimmen.

Lagenachweis im Testfall selbst: die Klartextzeile landet als Klartext im
Laufprotokoll (Assertion `strip`), die Zustandsdatei hält trotzdem nur die
Ereignis-Session `ses_attempt1`; unit-seitig ist mit Fall 16 belegt, dass
die Zustandsdatei die richtige Quelle ist. Rückmeldung als Befund an den
Coding-Agenten (Ambiguität der Quelle) — bewusst Test-Aufgabe, keine
Implementierungsvorschlagssetzung.

## 6. Aktueller Stand der Prüfsuiten (2026-11-07, nach den zwei Review-Fällen)

```
python3 -m unittest tests.unit.test_f25_session_continue
```
→ `Ran 16 tests`, 15 ok, 1 failure (nur Fall 14, Abschnitt 5).

```
python3 -m unittest discover -s tests/unit -v
```
→ 1015 Tests, 15 failures + 64 errors; Diff zum Baselinestand vor F25:
nur Fall 14 ist neu; ein der Basisliste zugehöriger Fehler
(`ERROR: test_every_checked_entry_keeps_its_proof_inside_the_block`) trat
diesmal nicht auf (umgebungsflüchtig, ohne Berührung durch den Test-Agenten).
Alle anderen Baselinestücke unverändert (Kosten-/Preisabbildungen,
`vibe_storage.BackupError: Read-only file system …/_toolchain/config-backups`,
`test_real_sandbox_…`, `test_without_override_no_model_flag_is_sent`,
`test_dry_run_explains_pi…`, 64 setUpClass-ERRORs).

## 7. Zuständigkeit und Grenzen

* Nur Abschnitte 1–4 stammen vollständig vom Test-Agenten und sind
  reproduzierbare Tatsachen (alle Befehle und Ausgaben wurden tatsächlich
  ausgeführt); Abschnitt 5 beschreibt den belegten Unterschied zwischen dem
  Reviewer-Kriterium und dem Stand `b523743`.
* Keine Commits durch den Test-Agenten; der Arbeitsstand umfasst
  `tests/unit/test_f25_session_continue.py` (neu) und
  `tests/unit/runner_support.py` (geändert) sowie diesen Bericht.
* Keine Modellkosten, keine echten externen Dienste, keine geheimen Daten;
  alle Läufer-Tests laufen isoliert in temporären Verzeichnissen.
