# Review B11 — Runde 1

Reviewer: code-reviewer (unabhängig, read-only)
Stand: Arbeitsbaum auf Branch `vibe/vibe-B11-1794563515065792053-2158170-9095`
(Worktree `vibe-B11-a2hTGT`), Ausgangscommit `b46b98d` (Basis `4ca632a`).
Verfahren: Vollständiger Arbeitsbaum-Austausch (Implementierung + Tests +
Doku), Baseline-Vergleich gegen den Integrationsstand; Testläufe wurden vom
Koordinator geliefert, vom Reviewer nicht eigenständig ausgeführt.

## Summary

- Critical: 0
- High: 0
- Medium: 4
- Minor: 4
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Kriterium | Status | Implementierung | Test/Nachweis |
|---|---|---|---|
| Stopp-Knopf auf Projektebene beendet Agentenauftrag samt Unter-/Enkelprozessen (No-Go) | PASS (mit Vorbehalt, s. Medium 4) | `bin/vibe-run.sh` (Prozessgruppe, `stop_agent_group`, `wait`, `PIPESTATUS`), `external_end` | `tests/unit/test_b11_stop_terminates_agents.py` (8 Fälle, echte Prozesse, echter tmux); Rotphase dieser 8 Fälle nicht unabhängig belegt |
| Subagent-Ausgabe live sichtbar | PASS (mit Vorbehalt, s. Medium 3) | `bin/vibe_runs.py` (`_capture_child_event`), `bin/vibe-web.py` (`/api/subagents`), `bin/web/app.js` (`outputView`) | `test_b11_stream_relay.py` (6), `test_b11_output_view_api.py` (8), `test_b11_output_ui.py` (8 Browser) |
| UI neu optimiert | PASS | `bin/web/app.js` (neue `outputView`), `bin/web/styles.css` (`bv-*`) | `test_b11_output_ui.py` (8 Vertragsfälle) |
| Neubau ohne Recycling von F19/F24/AP14 | PASS | grep: keine Treffer auf `outtabs|steer-card|subagents-card|agent-active|f19-controls|output-layout|output-side|outpane|subagent-list|subagent-count` unter `bin/web` | `test_b11_output_ui.py::LayoutAndRebuildTest.test_old_output_view_building_blocks_are_removed`; Löschung `test_ap14_output_ui.py`/`test_f24_output_tabs_ui.py` |
| API-Verträge: `/api/subagents` nur aktueller Lauf/kompakt, `/api/subagent-output` chronologisch (`order=asc`), Steer/Continue unverändert | PASS | `bin/vibe-web.py` | `test_b11_output_view_api.py` (8 Fälle); angepasste F19-/B6-Suiten |
| F25-Fortsetzungskette verträglich mit `--attempt` | PASS | `bin/vibe-run.sh` (`--attempt`), `bin/vibe_runs.py` (Versuchskontext) | F25-Suite end-to-end über den echten Läufer (16 OK) |

## Findings

- [Medium] `bin/vibe-run.sh` — Signallücke während der Preflight-Assistenz;
  Doku behauptet gegenteilige Abdeckung
  - Die HUP/TERM/INT-Traps werden erst nach `preflight_with_assist start`
    installiert. Die Preflight-Assistenz startet aber selbst einen Agenten in
    einer Prozessgruppe. Stirbt der Läufer in diesem Fenster an einem
    unabgefangenen Signal (z. B. `vibe stop` → `tmux kill-session` → SIGHUP),
    läuft der `EXIT`-Trap bei Bash nicht (ein `EXIT`-Trap wird bei Tod durch
    ein nicht abgefangenes Signal nicht ausgeführt) → die
    Preflight-Agentengruppe bleibt als Waise zurück, `register_finish` wird
    nicht ausgeführt. Betroffen ist auch das „end"-Preflight.
    `docs/features/B11.md` behauptet, der EXIT-Trap beende die Gruppe „bei
    jedem Ende des Läufers, auch … während der Preflight-Assistenz" — das ist
    für dieses Fenster nicht wahr.
  - Required fix: Das Spawn-/Wait-Fenster gegen Signale blockieren oder die
    HUP/TERM/INT-Traps vor dem ersten Preflight-Aufruf installieren;
    `docs/features/B11.md` an die tatsächliche Abdeckung anpassen; Testfall
    ergänzen (Läufer während der Preflight-Assistenz per HUP beenden →
    Agentengruppe endet, Registerzustand korrekt).
- [Medium] `bin/vibe-run.sh` — Race zwischen Hintergrundsstart und
  `AGENT_PID`-Zuweisung
  - Zwischen `) </dev/null &` und `AGENT_PID=$!` kann ein Signal-Trap feuern.
    `stop_agent_group` sieht dann einen leeren `AGENT_PID` und kehrt ohne
    Wirkung zurück; wegen `EXTERN_ENDED=1` wird der Stopp nicht wiederholt —
    die gestartete Agentengruppe läuft weiter.
  - Required fix: Das Fenster gegen Signale blockieren oder die Zuweisung so
    anordnen, dass der Trap nie einen leeren Wert sieht; Verhalten per
    Testfall mit gesteuertem Signal absichern.
- [Medium] `bin/vibe_runs.py` (mit `bin/vibe-web.py`) — Live-Ausgabe je
  Subagenten-Eintrag unbegrenzt
  - `_capture_child_event` hängt jeden Ereignistext an `entry["output"]` an,
    ohne Begrenzung; jede Änderung löst kompletten atomaren Rewrite + fsync
    der Zustandsdatei aus; `/api/subagents` liefert `output` ungekürzt bei
    2-Sekunden-Polling. `MAX_SUBAGENTS` (50) begrenzt nur die Eintragsanzahl,
    nicht die Bytes. Bei langen Subagentenläufen wachsen Zustandsdatei,
    API-Antwort und UI ungebremst.
  - Required fix: Definierte Begrenzung der Ausgabe je Eintrag (Byte-/Zeilen-
    budget mit festgelegtem Zuschnittverhalten, z. B. Tail) vereinbaren, in
    `docs/features/B11.md` dokumentieren und per Testfall mit großem
    Ausgabevolumen belegen.
- [Medium] `tests/unit/test_b11_stop_terminates_agents.py` — Rotphase der
  8 Stopp-Tests nicht unabhängig belegbar
  - Der Test-Agenten-Bericht belegt die Rotphase für 16 der 24 Fälle; für die
    8 Stopp-Tests wird sie nur auf eine mündliche Meldung des Primärauftrags
    gestützt — ein Protokoll des Fehlschlags gegen den Ausgangsstand fehlt.
  - Required fix: Rotphasenlauf der 8 Stopp-Tests gegen einen sauberen
    Checkout des Ausgangsstands nachholen und das tatsächliche Protokoll in
    den Test-Agenten-Bericht aufnehmen (Anforderung an den Test-Agenten).
- [Minor] `bin/vibe_runs.py` — Trim kann laufende Einträge verwerfen
  - `kept[-MAX_SUBAGENTS:]` schneidet bei mehr als 50 gleichzeitig laufenden
    Einträgen die ältesten laufenden ab; die Feature-Doku formuliert schärfer
    („immer erhalten") als der Code („bevorzugt").
  - Required fix: Semantik festlegen oder Doku-Formulierung angleichen; Fall
    per Test pinnen.
- [Minor] `tests/unit/test_b11_stream_relay.py` — `--attempt`-Pfad der
  Erfassung nicht direkt getestet
  - Alle 6 Erfassungstests rufen `stream_events` ohne `attempt`-Kontext auf;
    der Produktionspfad übergibt immer `--attempt`. Die Pinning-/Kind-
    Erfassungslogik des Versuchsmodus bleibt nur indirekt über F25 belegt.
  - Required fix: Mindestens einen Erfassungstestfall mit gesetztem
    `attempt`-Kontext ergänzen (beim Test-Agenten anfordern).
- [Minor] `bin/vibe-web.py` — `steer_project` prüft `tracked_sessions` über
  alle Einträge der Zustandsdatei
  - Die Zielprüfung nutzt alle Subagenten-Einträge statt nur der Einträge des
    aktuellen Laufs. Als vorbestehend verifiziert: identische Logik im
    Baseline-Stand. Nicht von B11 verursacht, aber B11 macht die Liste über
    die Live-Erfassung größer.
  - Required fix: Nicht in diesem Paket mischen — als AP14-Nachbereitung
    separat ticketen.
- [Minor] `bin/vibe-web.py` — Zeitfilter mit `run_start_epoch() = None`
  fall-open; Einträge mit `started = 0` verschwinden
  - Bei unlesbarem Registereintrag werden alle Einträge ausgeliefert
    (Überbleibsel früherer Läufe sichtbar), obwohl der Kommentar „Nur Einträge
    des aktuellen Laufs" verspricht. Umgekehrt fallen Einträge mit
    `started=0` unter einem aktiven Lauf durch den Vergleich weg.
  - Required fix: Semantik für beide Grenzfälle festlegen (dokumentiert) und
    per Test pinnen.

## Verification

- Change set reviewed: Ausgangscommit `b46b98d` … uncommitteter Arbeitsbaum.
- Checks with supplied output (nur gelieferte Meldungen des Koordinators, nicht
  eigenständig verifiziert): B11-Unit 22 OK; B11-Browser 8 OK; F25-Suite
  16 OK; Regressionen 63 OK; `bash scripts/verify.sh quick` Exit 0;
  `verify.sh full` 1703 Tests mit 2 vorbestehenden Fehlschlägen
  (`test_ap04_setup_harness`, `test_release` — Home-Pfad-Regel).
- Checks not independently run: alle Build-/Test-/Suitenläufe; die
  Testherkunft (Test-Agent) und die Rotphasen sind Berichtsangaben, außer den
  16 mit geliefertem Output belegten Fällen.
- Important areas inspected: `bin/vibe-run.sh` (Traps, Prozessgruppen,
  PIPESTATUS, `--attempt`, Preflight-Assistenz), `bin/vibe_runs.py`
  (Erfassung, Trim, `stream_events`), `bin/vibe-web.py` (Subagent-APIs, steer,
  stop, Zeitfilter), `bin/web/app.js` + `bin/web/styles.css` (neue
  `outputView`, `el()` mit Textknoten — kein innerHTML, kein XSS-Vektor),
  alle 4 B11-Testdateien samt `b11_harness.py`, Bereinigungs-Diffs der fremden
  Testdateien gegen den Baseline-Stand — ausschließlich testseitige
  Anpassungen, keine Feldsemantik abgeschwächt; `docs/import-manifest.json`
  (B11-Eintrag).
- Remaining risks: Die Signallücken sind durch Codeanalyse begründet, nicht
  durch einen reproduzierten Lauf; das Verhalten von `tmux kill-session`
  gegenüber dem Läufer wurde nur aus dem dokumentierten Stopp-Pfad
  abgeleitet. Die volle Breite der Regressionen beruht auf gelieferten
  Meldungen. Trilium-Dokumentation des Pakets kann aus dem Repository nicht
  verifiziert werden.

## Verdict

CHANGES REQUIRED
