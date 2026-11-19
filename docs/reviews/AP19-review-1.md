# Reviewantwort AP19 — Runde 1

Reviewer: unabhängiger code-reviewer, read-only, 2026-11-19.
Geprüfter Umfang: `b8b08e6..57cc5db` (Zweig
`vibe/vibe-AP19-1795039154711939108-299324-2397`, Arbeitskopie
`vibe-AP19-0es20i`; Arbeitsbaum sauber und byte-identisch mit `57cc5db`).
Der Reviewer konnte die Datei wegen seiner read-only-Werkzeugbeschränkung
nicht selbst anlegen; die Antwort ist wörtlich übernommen (bis auf diesen
 Kopfkasten).

---

# Review result

## Summary
- Critical: 0
- High: 1
- Medium: 2
- Minor: 4
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Kriterium | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: letzte Sessions auflisten, Standard 5, konfigurierbar, Suche/Projektfilter | PASS (mit Befund M1) | `bin/vibe:2291-2324` (`list`-Parser), `bin/vibe_runs.py:1045-1089` (`session_overview`, Rangfolge Limit), `bin/vibe_runs.py:1028-1042` (`limit`/`set_limit` 1..100) | `tests/unit/test_ap19_sessions_cli.py:279-415` (`test_list_…`, `test_limit_…`), `tests/unit/test_ap19_sessions_registry.py:492-573` (`OverviewLimitTest`); laut Testbericht Runde 2 21+18 OK, `verify.sh quick` Exit 0 |
| AK2: Session wiederfinden (Kennung, Zustand, Agent, Projektname, lesbare Zeit) | PASS | `bin/vibe_runs.py:1078-1088` (Join `runs.json` → `state`/`state_label`), `bin/vibe:2321-2324` (Ausgabe), `bin/web/app.js:204-231` | `tests/unit/test_ap19_sessions_registry.py:325-490` (Zustandsableitung), `tests/unit/test_ap19_sessions_cli.py:279-311`; Bericht Runde 2: 21 OK |
| AK3: Fortsetzen über CLI (`resume --session/--last/--aborted`) und Web-API (GET/POST) | PASS | `bin/vibe:2238-2289` (Projekt-/Session-/Aktiv-/Harness-Prüfung, `cmd_run(continue_session=…)`), `bin/vibe-web.py` GET/POST `/api/sessions` (Token, 404, Whitelist, `ok:false`) | `tests/unit/test_ap19_sessions_cli.py:479-651`, `tests/unit/test_ap19_sessions_api.py` (17 Fälle); Bericht Runde 2: 18+17 OK |
| AK4: exakte Wiederherstellung nach unerwartetem Abbruch (vor Laufende erfasst) | PASS | `bin/vibe-run.sh` (zwei `STREAM_FILTER`-Zuweisungen: Preflight ohne, Paketlauf mit `$RUN_ID`), `bin/vibe_runs.py:994-1026` (Upsert, `first_seen` bleibt), Capture im Filter | `tests/unit/test_ap19_runner_capture.py` 11 Fälle inkl. Hard-Abort/Verdrahtung; Bericht Runde 2: 11 OK |
| AK5: UI-Karte „Sessions“ (Tab Arbeit), Statuspillen, Zeit, Fortsetzen-Knopf, Pi-Hinweis, Leerzustand | PASS (mit Befund H1) | `bin/web/app.js:202-231` (Karte, `sessionTone`, `sessionTime`, ein einmaliger Load, DOM-only) | `tests/browser/test_ap19_sessions_ui.py` 7 Fälle laut Bericht Runde 2 OK; **Rotphase fehlt** (H1) |
| AK6: Rückwärtskompatibilität (bestehende Suiten/Regressionen) | PASS | keine Signaturänderung an `cmd_run`; optionale Argumente in `vibe_runs.py stream` | Regressionen 53 OK laut Bericht Runde 2; `tests/unit/test_baseline_inventory` 8 OK; `verify.sh quick` Exit 0 (geliefertes Artefakt, nicht von mir ausgeführt) |

## Findings

- [High] `docs/features/AP19.md:253-258` / `docs/reviews/AP19-test-agent-report.md:232,342-344` — Failing-first-Nachweis der Browser-Suite fehlt
  - Evidence: Die 7 UI-Fälle wurden am Basisstand `b8b08e6` nie ausgeführt (`No module named 'playwright'`, Runde 1). In Runde 2 war Playwright verfügbar; der Bericht belegt nur den grünen Lauf (`Ran 7 tests, OK`) und sagt ausdrücklich, die Rotphase sei „weiterhin nicht belegt“. Damit fehlt für die UI-Akzeptanz (AK5) jeder Nachweis, dass die Tests vor der Änderung fehlschlagen; die Regel „no evidence that the new test failed before the change“ ist erfüllt.
  - Required fix: Browser-Suite einmal gegen `b8b08e6` ausführen und Fehlschlagausgabe dokumentieren (oder begründet und technisch nachvollziehbar darlegen, warum ein Lauf gegen den Basisstand nicht möglich ist) und dieses Ergebnis in AP19.md/Testbericht aufnehmen.

- [Medium] `bin/vibe:2301-2302` + `bin/vibe_runs.py:1064-1069` — `sessions list --project NAME` löst den Namen relativ zum aktuellen Arbeitsverzeichnis auf
  - Evidence: Der Parser reicht `project = rest[position]` unverändert an `session_overview`, das `os.path.realpath(os.path.abspath(project))` gegen das CWD auflöst. Anders als bei `resume` (`ppath(name)`, `bin/vibe:2242`) und der API wird der Projektname nicht über `project_map()` aufgelöst. Ein Aufruf aus einem beliebigen Verzeichnis filtert dadurch falsch bzw. liefert keine Treffer. Der Test `test_list_filters_by_project_name` (`tests/unit/test_ap19_sessions_cli.py:376-395`) maskiert den Fehler, weil `self.root` als CWD gesetzt ist (`:177`) und die Testprojekte direkt unter `self.root` liegen (`:102-110`), sodass der nackte Name zufällig auf denselben Pfad zeigt.
  - Required fix: In `cmd_sessions` den Projektfilter über `ppath`/`project_map` auflösen (wie `resume`) und einen Test ergänzen, der aus einem abweichenden CWD mit Projektnamen filtert.

- [Medium] `bin/vibe_runs.py:974-981` — 100er-Obergrenze verwirft nach Insertionsreihenfolge, nicht nach `last_seen`
  - Evidence: `_write` schneidet `sessions[-100:]` ab, während `observe` (`:1006-1025`) bestehende Einträge in-place aktualisiert. Ein erneut beobachteter älterer Eintrag trägt danach das neueste `last_seen`, steht aber weiter an alter Listenposition und kann beim nächsten Schreiben verworfen werden – genau der Eintrag, der fortgesetzt werden soll. Der Test `test_observe_limits_the_register_to_the_newest_100_entries` (`tests/unit/test_ap19_sessions_registry.py:246-260`) beobachtet nur neue Kennungen und deckt diesen Fall nicht ab.
  - Required fix: Vor dem Kürzen nach `last_seen` sortieren (die zu behaltenden neuesten 100 bestimmen) und einen Test für erneutes Beobachten eines alten Eintrags an der Grenze ergänzen.

- [Minor] `docs/features/AP19.md:181-216` und `docs/baseline.md:159` — Teststand aus Runde 1 statt Runde 2
  - Evidence: AP19.md behauptet „Die Suiten wurden unverändert übernommen“ und dokumentiert weiterhin 2 Errors/„FAILED (errors=2)“ sowie „Tests wurden nicht verändert“; Runde 2 hat die beiden Methoden im Registry-Test korrigiert und alle 74 Fälle grün (`AP19-test-agent-report.md:298-349`). `baseline.md:159` nennt weiterhin „2 an Konstruktionsfehlern der Testsuite“.
  - Required fix: Testabschnitt und Prüfungszahlen in AP19.md sowie die Baseline-Zeile auf den Stand nach Runde 2 heben.

- [Minor] `docs/compatibility.md:92-94` — Satz zu Pi-Sessions ist invertiert
  - Evidence: „Die Session-Auflistung (AP19) listet auch Pi-Läufe, weil der Protokollfilter deren flüchtige Kennung bewusst nicht erfasst“ widerspricht sich selbst und der Implementierung: Pi-Kennungen werden nicht erfasst (`docs/features/AP19.md:150-153`), also können sie nicht gelistet werden; die Karte zeigt nur den Hinweis.
  - Required fix: Satz korrigieren zu „listet keine Pi-Läufe …“.

- [Minor] `docs/import-manifest.json:960` — falscher Dateiname im `grund`
  - Evidence: „session.json-Register“ statt `sessions.json` (implementiert in `bin/vibe_runs.py` als `sessions.json`). Rein dokumentarisch, aber manifestrelevant.
  - Required fix: Auf `sessions.json` korrigieren.

- [Minor] `bin/web/app.js:220` — Erfolgs-Toast bei `ok:false` ohne `message`
  - Evidence: `toast((r&&r.message)||'Fortsetzen gestartet.')` zeigt bei einer 403-/`ok:false`-Antwort ohne `message` fälschlich „Fortsetzen gestartet.“, obwohl die Aktion abgelehnt wurde. Die übrigen Karten prüfen `r.ok` (z. B. `:194`, `:199`).
  - Required fix: Bei `!r.ok` eine Fehlermeldung anzeigen; den Erfolgstext nur bei `ok:true` verwenden.

- [Minor] `bin/vibe_runs.py:1076` — `session_overview` bricht bei nicht-numerischem `last_seen` ab
  - Evidence: `int(item.get("last_seen") or 0)` wirft `ValueError`, obwohl `_read` (`:951-972`) nur `dict` und Session-String validiert und die Doku „defakte Datei“ als tolerierbar beschreibt. Eine manuell beschädigte `sessions.json` lässt damit Liste, API und UI scheitern statt den Eintrag zu überspringen.
  - Required fix: `last_seen` defensiv in eine Zahl überführen (ungültig → 0/überspringen) und einen Test mit beschädigtem Eintrag ergänzen.

Nicht beanstandet (ausdrücklich geprüft): Sperr- und Schreibverhalten der beiden Register (getrennte Lock-Dateien, atomare Schreibweise, keine rekursive Locknahme); Tokenpflicht beider neuer Routen und 404 für unbekannte Projekte; keine Shell-Auswertung von Session- oder Projektwerten (Argumentlisten, strenge Kennungsprüfung); `run_is_active`-Semantik unverändert; AP14-`/api/continue` unberührt; `cmd_run` unverändert außer dem bereits vorhandenen `continue_session`; DOM-only ohne innerHTML; einmaliges Laden ohne Polling-Aufblähung; Rotphase der vier Unit-Suiten belegt.

## Verification
- Change set reviewed: `b8b08e6..57cc5db` (Arbeitsbaum sauber, ein AP19-Commit); vollständige Diffs von `bin/vibe_runs.py`, `bin/vibe`, `bin/vibe-run.sh`, `bin/vibe-web.py`, `bin/web/app.js` sowie der fünf neuen Testdateien gelesen.
- Git commands run by me: `git log`, `git status`, `git diff` (read-only, soweit von der Berechtigung zugelassen); spätere Shell-Aufrufe wurden von der Berechtigung abgelehnt, daher erfolgte die Restprüfung über Datei-/Grep-Lesen.
- Checks with supplied output: Testbericht Runde 2 (21/11/18/17/7 OK, Regressionen 53 OK), `verify.sh quick` Exit 0, Manifest 57 Dateien OK, Rotphase der Unit-Suiten gegen `b8b08e6` – alles **geliefert, nicht von mir ausgeführt**.
- Checks not independently run: alle Build-/Test-/Verify-Kommandos; die Hash-/Manifestprüfung beruht auf dem gelieferten Log.
- Important areas inspected: `SessionRegistry` (`_read`/`_write`/`observe`/`limit`), `session_overview`, `cmd_sessions` (list/limit/resume), Runner-Verdrahtung in `vibe-run.sh`, GET/POST `/api/sessions`, `sessionsCard`/`sessionTone`/`sessionTime`, AP19.md, baseline.md, compatibility.md, import-manifest.json, Testbericht Runde 1+2.
- Remaining risks: (1) Browser-Rotphase fehlt (H1); (2) Projektfilter und 100er-Grenze sind nur durch CWD- bzw. Neuanlage-Tests abgedeckt (M1/M2); (3) dokumentierte Grenzen (Pi, Sandbox-Session-Speicher, getrimmtes Laufregister) bleiben bestehen.
