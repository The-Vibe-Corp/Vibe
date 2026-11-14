# Review B11 — Runde 2

Reviewer: code-reviewer (unabhängig, read-only)
Stand: Arbeitsbaum auf Branch
`vibe/vibe-B11-1794573038157202356-2311031-20895` (Worktree
`vibe-B11-HjVbKh`), Ausgangscommit `b46b98d`. Verfahren: Vollständiger
Arbeitsbaum-Austausch (Implementierung + Tests + Doku) gegen den
Ausgangsstand; Testläufe wurden vom Koordinator geliefert, vom Reviewer
nicht eigenständig ausgeführt. Fortsetzung des früheren B11-Laufs
(Worktree `vibe-B11-a2hTGT`, Runde 1 in `B11-review-1.md`); die alte
AP14-Ausgabeansicht ist verworfen, kein Recycling.

## Summary

- Critical: 0
- High: 0
- Medium: 1
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Kriterium | Status | Implementierung (file:line) | Test (file:method) / Nachweis |
|---|---|---|---|
| Stopp-Knopf auf Projektebene beendet den Agentenauftrag samt Unter-/Enkelprozessen, auch bei Signalignoranz (Ticket-No-Go) | PASS (mit Vorbehalt, s. Finding 1) | `bin/vibe-run.sh:295-353` (Prozessgruppe via `set -m`, `stop_agent_group` mit TERM→KILL-Eskalation, `wait`, `PIPESTATUS`), `bin/vibe-run.sh:693-712` (`external_end`, Signal-Traps vor dem ersten Preflight) | `tests/unit/test_b11_stop_terminates_agents.py` (11 Fälle, echte Prozesse, echter tmux, `StopEndpointRealTmuxTest` über `vibe stop` = derselbe Weg wie `/api/stop`); Rotphase von 6 der 11 Fälle gegen den Ausgangsstand `b46b98d` im Testbericht Kap. 7.1 mit tatsächlichen AssertionError-Protokollen belegt |
| Subagent-Ausgabe live sichtbar | PASS | `bin/vibe_runs.py:230-289` (`_child_event_lines`, `_capture_child_event`), `bin/vibe_runs.py:319-333` (Kind-Erkennung in `translate_event`), `bin/vibe_runs.py:631-682` (`stream_events` mit `run`-Kontext), `bin/vibe-web.py:844-878` | `test_b11_stream_relay.py` (8 Fälle, Rotphase von 5 im Testbericht Kap. 2.3 belegt), `test_b11_output_view_api.py`, `tests/browser/test_b11_output_ui.py` Fälle 1/2 (gelieferte Läufe: 8 OK) |
| UI der Ausgabeansicht neu optimiert | PASS | `bin/web/app.js:436-545` (neue `outputView`: Hauptagent + alle laufenden Subagenten gleichzeitig, `select[aria-label='Ziel']`, Fortsetzen nur bei gestopptem Lauf), `bin/web/styles.css:36-52` (`bv-*`-Layout, Mindesthöhen) | `tests/browser/test_b11_output_ui.py` (8 Fälle inkl. Höhen-Nutzung, Tastatur, Altbausteine-Entfernung); gelieferte Läufe: 8 OK |
| Neubau ohne Recycling von AP14/F24/F19-Oberfläche | PASS | grep über `bin/web` auf `outtabs\|steer-card\|subagents-card\|agent-active\|f19-controls\|output-layout\|output-side\|outpane\|subagent-list\|subagent-count\|continue-bar\|agentTabs`: 0 Treffer; `agentTabs`/`steerCard`/`subagentCard`/AP14-Fortsetzenleiste im Diff vollständig entfernt | `test_b11_output_ui.py::LayoutAndRebuildTest.test_old_output_view_building_blocks_are_removed`; Löschung `tests/browser/test_ap14_output_ui.py` und `test_f24_output_tabs_ui.py` (Bereinigung je Einzelfall im Testbericht Kap. 3.1/3.2). Die verbleibende `logView`-Karte ist Basisbestand vor AP14 und dient nur als Rückfall für Prüfläufe/projektferne Läufe — kein AP14-Recycling |
| Ausgabebudget (Runde-1 Medium 3): Tail-Semantik, Konsistenz Filter/API | PASS | `bin/vibe_runs.py:110-141` (`MAX_SUBAGENTS=50`, `MAX_SUBAGENT_OUTPUT_BYTES=64 KiB`, `output_tail` mit Multibyte-sicherem Zuschnitt), `bin/vibe_runs.py:285-288,403,520,541` (alle Schreibpfade budgetiert), `bin/vibe-web.py:166-186` (`MAX_LIST_OUTPUT_BYTES=4 KiB`, `listed_subagent` nutzt denselben `output_tail`) | `test_b11_stream_relay.py::OutputBudgetTest` (64-KiB-Tail, Rotphase mit konkreter Messung 248382 > 65536) und `test_b11_output_view_api.py::OutputBudgetTest` (4-KiB-Tail, Rotphase 200022 > 4096); Semantik konsistent: 64-KiB-Zustand, 4-KiB-Liste, Volltext via `/api/subagent-output` |
| Signallücke während Preflight-Assistenz (Runde-1 Medium 1) | PASS | `bin/vibe-run.sh:697-713` — HUP/TERM/INT-Traps stehen jetzt vor `preflight_with_assist start`; `external_end` beendet zusätzlich die Agentengruppe (Zeile 707) | `test_b11_stop_terminates_agents.py::PreflightAssistStopTest` und `::EndPreflightAssistStopTest` (Verhaltens-Pins, grün); Testbericht Kap. 7.2 B1a/B1b dokumentiert, dass die ursprüngliche EXIT-Trap-Lücke auf bash 5.3.9 nicht reproduzierbar ist — Fix trotzdem portabel sinnvoll umgesetzt |
| `--attempt`/F25-Verträglichkeit | PASS | `bin/vibe-run.sh:553` (`--attempt` am Stream-Filter), `bin/vibe_runs.py:319-333` (Versuchskontext), `bin/vibe_runs.py:636-682` (`_track_unknown_session`, `_promote_text_only_attempt`) | `test_b11_stream_relay.py::AttemptContextTest` (direkter Fall, Review Minor 2); F25-Suite 16 OK (geliefert) |
| Runde-1 Medium 4 (Rotphasenprotokoll der Stopp-Tests) | PASS | — | `docs/reviews/B11-test-agent-report.md` Kap. 7.1: eigener Lauf gegen `git archive b46b98d` in isoliertem Verzeichnis, 6 rot mit Protokollauszügen (überlebende PIDs, weiterlaufende Ticks) |
| Runde-1 Minor 1/2/4 | PASS | `bin/vibe_runs.py:106-109,179-190` (Formulierung „bevorzugt" stimmt mit Code), `bin/vibe-web.py:186-197,858-870` (dokumentierte fail-open-Semantik) | `AttemptContextTest`, `RunTimeFilterTest` (B5a/B5b, B5b mit Rotphasenbeleg) |
| XSS-Sicherheit der neuen Ansicht | PASS | `bin/web/app.js:12` (`el()` nur setAttribute/Textknoten), `bin/web/app.js:445-545` (Ausgabe ausschließlich über `pre.textContent`, keine `innerHTML`-Verwendung im Diff) | Indirekt über Browser-Suite (`assert_clean_page`, keine pageerrors); kein new innerHTML-Code |
| Arbeitskopie enthält nur B11-Änderungen | PASS | `git status --short`: ausschließlich die 11 bekannten B11-Dateien + 6 neue B11-Dateien; `scripts/verify.sh` und Prüfwerkzeugkette unangetastet | — |

## Findings

- [Medium] `bin/vibe-run.sh:346-347` — Race zwischen Hintergrundsstart und
  `AGENT_PID`-Zuweisung ist im Code nicht behoben (Runde-1 Medium 2)
  - Evidence: Zwischen `) </dev/null &` (Zeile 346) und `AGENT_PID=$!`
    (Zeile 347) kann ein Signal-Trap feuern. `stop_agent_group`
    (`bin/vibe-run.sh:300-309`) kehrt bei leerem `AGENT_PID` wirkungslos
    zurück; `external_end` setzt `EXTERN_ENDED=1`, verhindert damit jede
    Wiederholung und beendet den Läufer — die gerade gestartete
    Agentengruppe läuft als Waise weiter. Das ist exakt der im Ticket als
    „no go" bezeichnete Zustand, wenn auch in einem Fenster von
    Mikrosekunden. Runde 1 forderte als Required fix eine codeseitige
    Blockierung des Fensters oder eine Anordnung, bei der der Trap nie
    einen leeren Wert sieht. Geliefert wurde stattdessen nur der
    Toleranzlauf
    `StopAroundStartTest.test_repeated_hup_around_the_attempt_start_leaves_no_orphan`
    — der Testbericht (Kap. 7.2 B2) räumt selbst ein: „Ein grüner
    Einzellauf schließt das Fenster nicht aus … Keine Rotphase messbar —
    dokumentiert, nicht belegt für die Fensterfreiheit." Die vier
    Wiederholungen (Verzug 0/20/50/200 ms nach einer Protokollmarke vor dem
    Spawn) können das Mikrosekunden-Fenster grundsätzlich nicht gezielt
    treffen.
  - Required fix: Das Fenster deterministisch schließen oder die
    Restrisiko-Entscheidung explizit treffen und dokumentieren. Konkret
    (Auswahl freigestellt, keine Codeanweisung): `stop_agent_group` bei
    leerem `AGENT_PID` auf die tatsächlichen Hintergrundprozesse des
    Läufers zurückgreifen lassen (z. B. Gruppen über `jobs -p` ermitteln),
    oder die Trap-Reihenfolge/`AGENT_PID`-Führung so ändern, dass der Trap
    die Gruppe auch im Fenster findet. Anschließend den Toleranzfall
    behalten und in `docs/features/B11.md` die verbleibende Grenze entweder
    streichen (Fix) oder als akzeptiertes, begründetes Restrisiko mit
    Begründung festhalten.
- [Minor] `docs/features/B11.md:233-237` — Zähler für `verify.sh full`
  widerspricht dem gelieferten Prüfprotokoll
  - Evidence: Die Doku nennt „1711 Tests, 2 Fehlschläge". Der Koordinator
    hat für den aktuellen Lauf 3 Fehlschläge geliefert (zusätzlich
    `test_real_sandbox_allows_write_dirs`, angeblich am Baseline-Stand
    identisch fehlgeschlagen). Der Prüfbericht in der Paketdoku muss den
    tatsächlichen Protokollstand wiedergeben. Nicht independently
    verifiziert — beide Angaben sind Berichte; der Widerspruch bleibt
    bestehen.
  - Required fix: Kapitel „Prüfungen" in `docs/features/B11.md` an das
    tatsächliche full-Protokoll anpassen (3 vorbestehende Fehlschläge mit
    Baseline-Abgleich nennen).
- [Minor] `docs/features/B11.md:256-260` — Runde-1 Minor 3 (Steer-Ziel-
  prüfung über alle Zustandseinträge) ist ausgegrenzt, aber nicht separat
  ticketet
  - Evidence: `steer_project` prüft die Ziel-Session gegen alle Einträge
    der Zustandsdatei statt nur der Einträge des aktuellen Laufs
    (`bin/vibe-web.py:502-519`, vorbestehend, im Baseline identisch).
    Runde 1 forderte als Required fix: „als AP14-Nachbereitung separat
    ticketen". In `TICKETS.md` und `FEEDBACK.md` existiert kein
    entsprechender Eintrag; die Grenze ist nur in der Feature-Doku
    vermerkt.
  - Required fix: Follow-up-Eintrag in `TICKETS.md`/`FEEDBACK.md` anlegen
    oder die Ausgrenzung an der Stelle dokumentieren, an der der Workflow
    sie wiederfindet (Ticketliste).
- [Minor] `bin/vibe_runs.py:283-288` mit `save_subagent_state` (Zeile
  172-178) — je geändertem Ereignis kompletter Rewrite + `fsync` der
  Gesamtzustandsdatei
  - Evidence: Jede Zustandsänderung (jetzt auch jede Kind-Ereigniszeile)
    schreibt die Datei neu. Mit 50 Einträgen à 64-KiB-Tail sind bis zu
    ~3,2 MiB je Ereignis möglich; auf FUSE/NTFS (dokumentierte
    Zielumgebung) ist das spürbar. Das Wachstum ist begrenzt (Runde-1
    Medium 3 damit gelöst), aber die Schreibamplifikation pro Ereignis ist
    im Test nicht messend abgedeckt (die Budget-Tests prüfen Größe, nicht
    Schreibleistung).
  - Required fix: Kein Blocker. Falls auffällt: Schreibfrequenz begrenzen
    (z. B. throttle je Eintrag) oder Begründung in der Feature-Doku
    ergänzen; Testfall erst beim Test-Agenten anfordern.

## Verification

- Change set reviewed: Ausgangscommit `b46b98d` … uncommitteter Arbeitsbaum
  (Branch `vibe/vibe-B11-1794573038157202356-2311031-20895`); vollständiger
  `git diff HEAD --stat` (553/−1604 Zeilen) und Datei-Diffs von
  `bin/vibe-run.sh`, `bin/vibe_runs.py`, `bin/vibe-web.py`, `bin/web/app.js`,
  `bin/web/styles.css`, `docs/import-manifest.json` sowie alle vier neuen
  B11-Testdateien, `runner_fixtures` und die Bereinigungs-Diffs von
  `test_output_view_f19_api.py`, `test_b6_pi_events.py`,
  `test_f20_harness_ui.py` vollständig gelesen.
- Checks with supplied output (vom Koordinator, von mir nicht eigenständig
  ausgeführt): B11-Unit 30 OK; B11-Browser 8 OK; Regressionen 92 OK;
  `test_f20_harness_ui` 10 OK; `verify.sh quick` Exit 0; `verify.sh full`
  1711 Tests mit 3 als vorbestehend ausgewiesenen Fehlschlägen (2
  dokumentierte Baseline + 1 am Baseline identisch). Testherkunft und
  Rotphasen stütze ich auf den Test-Agenten-Bericht; die Rotphasen der 6
  Stamm-Stopp-Fälle, B3a, B3b und B5b sind dort mit konkreten
  Fehlerprotokollen belegt.
- Checks not independently run: alle Build-/Test-/Suitenläufe,
  Syntaxprüfung, SHA-256/Größenabgleich von `docs/import-manifest.json`
  gegen die geänderten Dateien (keine Rechte für Nicht-Git-Befehle),
  `verify.sh` in beiden Stufen.
- Important areas inspected: Prozessgruppen-/Signalumsetzung inkl.
  Trap-Reihenfolge und `wait`-Pfad in `bin/vibe-run.sh`; Erfassungs-,
  Trim-, Tail- und Versuchskontextlogik in `bin/vibe_runs.py`;
  Subagent-APIs, Zeitfilter, steer/continue in `bin/vibe-web.py`; neue
  `outputView` samt Moduswechsel (`agent`/`legacy`, verify-Pinning) in
  `bin/web/app.js`; `bv-*`-Layout in `styles.css`; B11-Testdateien und
  Fixtures auf Abschwächung (keine gefunden; alle Streichungen betreffen
  ausschließlich die verworfene AP14/F24-Oberfläche und sind je Einzelfall
  im Testbericht Kap. 3 begründet); Manifest-Eintrag B11.
- Remaining risks: Das Mikrosekunden-Race (Finding 1) ist durch Codeanalyse
  begründet, nicht durch einen reproduzierten Lauf; die Mannigfaltigkeit
  echter Harnesses (z. B. `setsid`-Enkelprozesse, die der Prozessgruppe
  entkommen) wurde nicht geprüft. Manifest-Prüfsummen unabhängig ungeprüft.
  Trilium-Dokumentation des Pakets kann aus dem Repository nicht verifiziert
  werden (AGENTS-Pflicht vor Abschluss; liegt beim Koordinator). Der
  Abgleich, ob `test_real_sandbox_allows_write_dirs` am Baseline-Stand
  identisch scheitert, beruht auf der Koordinatorangabe.

## Verdict

CHANGES REQUIRED
