# Reviewantwort AP19 — Runde 2

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-19.
Geprüfter Bereich: `57cc5db..b5ee2cd` (Umsetzung der Runde-1-Befunde),
Gesamtsicht `b8b08e6..b5ee2cd`. Arbeitskopie: `vibe-AP19-0es20i`, Branch
`vibe/vibe-AP19-1795039154711939108-299324-2397`, HEAD `b5ee2cd`.
Der Reviewer konnte die Datei wegen seiner read-only-Werkzeugbeschränkung
nicht selbst anlegen; die Antwort ist wörtlich übernommen (bis auf diesen
 Kopfkasten).

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Befunde aus Runde 1

| # | Befund | Status | Umsetzung (file:line) | Beleg |
|---|---|---|---|---|
| 1 | [High] Browser-Rotphase fehlte | **behoben** | `docs/features/AP19.md:222-233`; `docs/reviews/AP19-test-agent-report.md:419-449` | Reproduktion gegen `b8b08e6` im temporären Worktree: `Ran 7 tests in 145.278s, FAILED (errors=7)`, je Fall Timeout auf die fehlende Sessions-Karte; Worktree mit `git worktree remove --force` entfernt, `git worktree list` bestätigt. Zusätzlich Erstlauf 18.11. durch den Koordinator (`Ran 7 tests in 143.694s, FAILED (errors=7)`) in AP19.md und im Bericht dokumentiert. Keine Widersprüche zwischen beiden Stellen. |
| 2 | [Medium] `sessions list --project NAME` löste relativ zum CWD auf | **behoben** | `bin/vibe:2297-2305` (`project = ppath(rest[position])`, Kommentar „AP19/Review M1“) | Neuer Fall `tests/unit/test_ap19_sessions_cli.py:416-484` (`ProjectFilterCwdTest.test_list_project_filter_works_from_a_foreign_cwd`) mit zwei Unterfällen: fremdes CWD → Exit 0 und `ses_proj` sichtbar; unbekannter Name → Exit != 0, Name in der Meldung, kein Traceback. Rotphase gegen `57cc5db`: `failures=2` (`AP19-test-agent-report.md:379-384`), Grünphase Teil des gelieferten Laufs „Ran 70 tests, OK“. Der Fall nagelt die Erwartung fest; keine abgeschwächte Assertion erkennbar. |
| 3 | [Medium] 100er-Obergrenze verwarf nach Einfügungsreihenfolge | **behoben** | `bin/vibe_runs.py:982-999` | `_write` bestimmt die zu behaltenden 100 über `sorted(..., key=(seen_at(index), index))[-100:]`, behält die Originalreihenfolge der Verbleibenden und lässt Listen ≤100 unverändert. Gleichstand ist durch den Index-Tiebreaker deterministisch. Neuer Fall `tests/unit/test_ap19_sessions_registry.py:575-616` prüft `ses_001`-Erhalt, Wegfall von `ses_002`, exakt 100 Einträge und die Übersichtsreihenfolge `ses_neu, ses_001, ses_100`. Rotphase `failures=1` (`AP19-test-agent-report.md:397-402`), Grünphase 23/23 OK. |
| 4 | [Minor] `session_overview` brach bei unlesbarem `last_seen` ab | **behoben** | `bin/vibe_runs.py:922-927` (`_epoch_number`), `:1102-1116` (Skip, `first_seen` defensiv `0`, stabile Sortierung über Zahlenwerte) | Neuer Fall `tests/unit/test_ap19_sessions_registry.py:624-654` (`OverviewRobustnessTest.test_overview_skips_entries_with_corrupt_last_seen`): `"last_seen": "abc"` wird übersprungen, `ses_ok` bleibt. Rotphase `errors=1` (`AP19-test-agent-report.md:414-417`). Nur unlesbares `last_seen` führt zum Skip; ein Eintrag mit lesbarem `last_seen`, aber fehlendem/defektem `project`, `name`, `agent` oder `run_id` bleibt erhalten (Felder werden zu `""`/`unknown`/`0`). |
| 5 | [Minor] Doku-Stand Runde 1 statt Runde 2/3 | **behoben** | `docs/features/AP19.md:177-253`; `docs/baseline.md:159,244` | AP19.md nennt jetzt 77 Fälle (23/11/19/17/7), beschreibt die Runde-2-Korrektur ausdrücklich als Test-Agenten-Korrektur (Zeilen 194-202) und dokumentiert Runde 3 sowie H1. Keine „2 Errors“-/„unverändert übernommen“-Aussagen mehr; `baseline.md` führt 19 CLI- und 23 Registry-Fälle sowie 77 Gesamtfälle. Eigene Zählung der Testmethoden bestätigt 23+11+19+17+7 = 77. |
| 6 | [Minor] Invertierter Pi-Satz in `compatibility.md` | **behoben** | `docs/compatibility.md:92-94` | „Die Session-Auflistung (AP19) listet keine Pi-Läufe, weil der Protokollfilter deren flüchtige Kennung bewusst nicht erfasst …“ — stimmt mit der Implementierung und `AP19.md:257-259` überein. |
| 7 | [Minor] `session.json` statt `sessions.json` im Manifest | **behoben** | `docs/import-manifest.json:960` | `grund` nennt jetzt „sessions.json-Register“ und die Reviewkorrekturen (Projektauflösung, Kürzung nach `last_seen`, Skip beschädigter Zeitwerte, Toast, Lint-Kommentar). Geliefertes `check-import-manifest.py`: „OK: 57 Dateien stimmen …“, Exit 0. |
| 8 | [Minor] Erfolgs-Toast bei `ok:false` | **behoben** | `bin/web/app.js:221` | `toast(r&&r.ok?((r.message)||'Fortsetzen gestartet.'):'Fortsetzen abgelehnt: '+((r&&r.message)||'Unbekannter Grund.'))` — Erfolgstext nur bei `ok:true`, sonst Ablehnungsmeldung. Kein eigener Testfall; laut Vorgabe bewusst akzeptiert, Browser-Suite weiter 7/7 OK (geliefert). |

## Neu seit Runde 1

| # | Punkt | Einordnung | Beleg |
|---|---|---|---|
| 9 | Pylint-Kommentar an der neuen `_real`-Stelle; verbleibende F28-`function-redefined` | **Kommentar vorhanden; Restbefunde vorbestehend, nicht AP19** | `bin/vibe-web.py:1277` trägt `# pylint: disable=protected-access` wie die Schwesternstellen `:463` und `:1018`. Die Dublette `reload_ui_data` (aktuell `:683` und `:722`) ist laut `docs/reviews/AP18-review-1.md:59` bereits vor AP19 vorhanden (dort `669-744`); AP19 verschiebt sie nur. Pylint selbst wurde von mir nicht ausgeführt. |
| 10 | Home-Pfad-Hygiene im Testbericht | **behoben** | `docs/reviews/AP19-test-agent-report.md:471-495`; eigene Suche `grep -n "/home/"` findet nur noch die Konventionsform `/home/nutzer/...` und den Suchbefehl selbst, keinen echten Nutzer-Home-Pfad. Geliefert: beide Hygiene-Fälle (`TrackedContentHygieneTest`, `ReleaseBuildTest`) `Ran 2 tests, OK`. |

## Zusatzprüfungen (neue Defekte der Umsetzung)

- `_write`-Kürzung: Deterministisch bei Gleichstand (`(last_seen, index)`), Originalreihenfolge bleibt erhalten, bei ≤100 Einträgen kein Eingriff; unlesbare Zeitwerte zählen als 0. Kein eigener Gleichstands-Test, aber durch den Sortierschlüssel eindeutig festgelegt.
- `ppath` im `list`-Zweig: `resume` nutzt bereits `ppath` (`bin/vibe:2242`) und ist unverändert; `--limit` und Suchtext werden weiterhin im selben Parser verarbeitet. Keine Regression der übrigen Listenoptionen erkennbar.
- Übersicht: Skip erfolgt ausschließlich bei `_epoch_number(last_seen) is None`; ein Eintrag mit lesbarem `last_seen` und sonstigen Defekten bleibt erhalten. `first_seen` wird auf `0` gesetzt; die Sortierung ist stabil (nur `last_seen` als Key).
- Neue Tests: keine Skips, keine leeren Testkörper, keine `assertTrue(True)`-Muster; die neuen Fälle prüfen Exit-Codes, konkrete Kennungen und Reihenfolgen.

## Findings

- [Minor] `bin/vibe_runs.py:922-927` — `_epoch_number` behandelt `bool` als gültige Zahl
  - Evidence: `int(True)` liefert `1`, daher wird `"last_seen": true` nicht übersprungen, sondern als `1` geführt; `"first_seen": true` wird zu `1` statt `0`. Das widerspricht der projektinternen Behandlung in `observe` (`:1011-1016`) und `_read` (`:968-970`), die `bool` ausdrücklich als ungültig verwerfen. Kein Absturz, nur ein schmaler Korruptions-Randfall; der neue Robustheitstest deckt nur `"abc"` ab.
  - Required fix: In `_epoch_number` `isinstance(value, bool)` als unlesbar (`None`) behandeln und den Robustheitstest um einen `bool`-Unterfall ergänzen. Nicht blockierend.

- [Minor] `docs/features/AP19.md:95-97` — CLI-Abschnitt dokumentiert die neue Fehlersemantik von `--project` nicht
  - Evidence: Der funktionale Abschnitt sagt weiterhin nur „ohne Treffer erscheint eine klare Leerzeilenmeldung“; seit M1 bricht ein unbekannter Projektname jedoch über `ppath` mit Exit != 0 und Meldung ab (`bin/vibe:2305`; Test `test_ap19_sessions_cli.py:468-483`). Die Test-Sektion (`AP19.md:210-212`) und der Testbericht nennen das Verhalten, die Feature-Beschreibung nicht.
  - Required fix: Im CLI-Abschnitt einen Satz ergänzen, dass `--project` über die Projektkarte aufgelöst wird und unbekannte Namen mit klarer Meldung abbrechen. Nicht blockierend.

## Verification

- Change set reviewed: `57cc5db..b5ee2cd` und Gesamtsicht `b8b08e6..b5ee2cd`. Den Git-Diff konnte der Reviewer **nicht selbst abrufen** (Shell-Berechtigung verweigert); er hat den vollständigen aktuellen Dateistand der genannten Produktions-, Test- und Dokumentationsdateien gelesen und mit dem Runde-1-Stand aus seinem Review verglichen.
- Git commands run by me: keine erfolgreich; `shell` wurde von der Berechtigung abgelehnt. Arbeitsbaum-Sauberkeit und HEAD sind Angaben der Aufgabenstellung, nicht vom Reviewer per Git verifiziert.
- Checks with supplied output (geliefert, nicht vom Reviewer ausgeführt): 70 Unit-Tests OK; 7 Browser-Tests OK; 53 Regressionstests OK; 8 Baseline-Tests OK; 2 Hygiene-Tests OK; `verify.sh quick` Exit 0; `check-import-manifest.py` OK (57 Dateien); Rotnachweis der drei neuen Fälle gegen `57cc5db`: `failures=3, errors=1`; Browser-Rotphase gegen `b8b08e6`: `Ran 7 tests in 145.278s, FAILED (errors=7)`.
- Checks not independently run: alle Build-, Test-, Verify- und Pylint/Kommandos; die Manifest-Hashes und die Testläufe beruhen auf den gelieferten Artefakten.
- Important areas inspected: `_write`/`observe`/`session_overview`/`_epoch_number` (`bin/vibe_runs.py`), `cmd_sessions`-Listenpfad (`bin/vibe`), Toast (`bin/web/app.js`), `_real`-Kommentar und `reload_ui_data`-Dublette (`bin/vibe-web.py`), die drei neuen Testfälle, AP19.md, baseline.md, compatibility.md, import-manifest.json, Testbericht Runde 3, Hygieneabschnitt.
- Remaining risks: (1) Kein eigener Git-Diff und kein eigener Pylint-Lauf des Reviewers; die Einordnung der `reload_ui_data`-Dublette als vorbestehend stützt sich auf `AP18-review-1.md:59` — vom Koordinator zusätzlich per `git show b8b08e6:bin/vibe-web.py | grep -n "def reload_ui_data"` nachgewiesen (Treffer bei 669 und 708 am Basiscommit). (2) Die zwei genannten Minor-Punkte bleiben offen, sind aber nicht blockierend. (3) `tests.browser.test_b11_output_ui` 8/8 erscheint in AP19.md als früherer Lauf; die App.js-Änderung ist auf `sessionsCard` beschränkt, daher geringes Risiko. (4) Arbeitsbaum-Sauberkeit laut Vorgabe, vom Koordinator per `git status` bestätigt.

**Abschluss:** Verdict: **PASS** · Critical 0 · High 0 · Medium 0 · Minor 2.
