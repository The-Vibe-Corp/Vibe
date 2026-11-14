# Review B11 — Runde 3

Reviewer: code-reviewer (unabhängig, read-only)
Stand: Arbeitsbaum auf Branch `vibe/vibe-B11-1794584078598926007-2578957-11535`
(Worktree `vibe-B11-xZoVIR`), Ausgangscommit `b46b98d`. Verfahren:
Fortsetzung der Runden 1 und 2 (`B11-review-1.md`, `B11-review-2.md`);
der Arbeitsstand des abgebrochenen Laufs (`vibe-B11-HjVbKh`) wurde
byte-identisch in diesen Arbeitsbaum übernommen, die Runde-2-Befunde sind
umgesetzt und der Koordinator hat die tatsächlichen Prüfläufe geliefert.
Testläufe wurden vom Koordinator geliefert, vom Reviewer nicht eigenständig
ausgeführt.

## Stufenlimit (Hinweis zum Verfahren)

Das Stufenlimit dieses Review-Auftrags ist vor dem letzten Kontrollschritt
(Name des Feature-Branch über Git-Kommando unabhängig zu verifizieren)
erreicht; die Shell-Berechtigung verweigerte darüber hinaus mehrere
Git-Befehle (`git branch --show-current`, `git status -sb`,
`git ls-files`). Alle inhaltlichen Prüfschritte des Runde-3-Auftrags sind
abgeschlossen; der Bericht ist vollständig und urteilsfähig. Der
Branch-Name bleibt als einzige nicht verifizierte Angabe markiert.

## Summary

- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

## Acceptance criteria

| Kriterium | Status | Implementierung (file:line) | Test (file:method) / Nachweis |
|---|---|---|---|
| Stopp-Knopf auf Projektebene beendet Agentenauftrag samt Unter-/Enkelprozessen auch bei Signalignoranz (Ticket-No-Go) | PASS | `bin/vibe-run.sh:295-321` (Prozessgruppe, `stop_agent_group`, EXIT-Trap), `bin/vibe-run.sh:322-361` (`run_agent_in` mit `set -m`, `wait`, `PIPESTATUS`), `bin/vibe-run.sh:701-716` (`external_end`, HUP/TERM/INT-Traps vor dem ersten Preflight) | `tests/unit/test_b11_stop_terminates_agents.py` (14 Fälle); Rotphase der 6 Stamm-Stopp-Fälle gegen `b46b98d` im isolierten Klon mit konkreten AssertionError-Protokollen belegt (Testbericht Kap. 7.1: überlebende PIDs, weiterlaufende Ticks); geliefert: B11-Unit 33 OK |
| Spawnfenster-Race (Runde-2 Medium) durch `jobs -p`-Rückfall geschlossen | PASS | `bin/vibe-run.sh:300-317` — bei leerem `AGENT_PID` greift `stop_agent_group` auf `jobs -p` zurück; unter `set -m` ist die Auftrags-PID zugleich PGID | `test_b11_stop_terminates_agents.py::StopAgentGroupFallbackTest` (3 Fälle: Trap bei leerer Kennung beendet die laufende Gruppe inkl. KILL-Eskalation, Harmlosigkeit ohne Jobs, unveränderter Normalpfad); Rotphase von Fall 1 mit 3-wiederholtem Exit 1 dokumentiert (Testbericht Kap. 8.3) — die Fensterlage wird hergestellt, nicht zufällig getroffen |
| `jobs -p`-Rückfall ist nicht harmlos-falsch | PASS | `bin/vibe-run.sh:305-308` — Annahme „einziger Hintergrundauftrag" ist belegbar: die einzige Backgrounding-Stelle des Skripts ist `bin/vibe-run.sh:354`; die Preflight-Assistenz nutzt dieselbe `run_agent_in` (`bin/vibe-run.sh:689`), die mit `wait` aufräumt, sodass `jobs -p` nie einen veralteten Eintrag neben dem neuen Auftrag liefern kann | Code-Analyse (grep auf `&$`: nur Zeile 354) + `StopAgentGroupFallbackTest.test_stop_with_unassigned_agent_pid_and_no_jobs_is_harmless` pinnt die Harmlosigkeit, `…_assigned_agent_pid_kills_that_group` den Normalpfad |
| Subagent-Ausgabe live sichtbar | PASS | `bin/vibe_runs.py:231-289` (`_child_event_lines`, `_capture_child_event`), `bin/vibe_runs.py:319-353` (Kind-Erkennung inkl. `--attempt`), `bin/vibe_runs.py:636-682` (`stream_events` mit Versuchskontext) | `test_b11_stream_relay.py` (8 Fälle, Rotphase u. a. B3a mit `AssertionError: 248382 not less than or equal to 65536`), `test_b11_output_view_api.py` (11 Fälle), `tests/browser/test_b11_output_ui.py::SimultaneousAgentsTest` (geliefert: Browser 18 OK) |
| Neue outputView: kein Tab-Gate, alle laufenden Subagenten gleichzeitig, Ziel-select, Fortsetzen nur gestoppt | PASS | `bin/web/app.js:436-545` (`outputView`: Hauptagent dauerhaft sichtbar, `bv-subs` nebeneinander, natives `select` mit `aria-label="Ziel"`, `cont.hidden=!(session&&!running)`, nur `textContent`/`el()` — kein `innerHTML`), `bin/web/styles.css:36-52` | `test_b11_output_ui.py::SimultaneousAgentsTest`, `::SteerTargetTest` (POST enthält exakt die gewählte Session), `::ContinueTest` (Knopf nur gestoppt), `::LayoutAndRebuildTest::test_output_view_uses_the_available_height` (≥65 % Panel, ≥40 % Hauptansicht, kein Unterlauf), `::test_old_output_view_building_blocks_are_removed` |
| Neubau ohne Recycling der AP14/F24/F19-Oberfläche | PASS | grep über `bin/web/app.js` auf `outtabs|steer-card|subagents-card|agent-active|f19-controls|output-layout|output-side|outpane|subagent-list|subagent-count|continue-bar|continuebar|agentTabs`: **0 Treffer**; `innerHTML|insertAdjacentHTML|document.write`: 0 Treffer (nur der Dokumentkommentar) | `test_b11_output_ui.py::LayoutAndRebuildTest::test_old_output_view_building_blocks_are_removed`; Alt-Suiten `test_ap14_output_ui.py`/`test_f24_output_tabs_ui.py` gelöscht, `test_f20_harness_ui.py` bereinigt (je Einzelfall im Testbericht Kap. 3.1-3.6 begründet; keine B11-Assertion abgeschwächt) |
| `--attempt`-Kontext und F25-Verträglichkeit | PASS | `bin/vibe-run.sh:561` (`--attempt` am Stream-Filter), `bin/vibe_runs.py:319-333` (erste Session pinnt, abweichende sind Kinder), `bin/vibe_runs.py:644-682` (`_track_unknown_session`, `_promote_text_only_attempt` für Rückwärtskompatibilität) | `test_b11_stream_relay.py::AttemptContextTest::test_attempt_pins_the_first_session_and_takes_others_as_children` (direkt, ohne F25-Umweg); F25-Suite 16 OK (geliefert) |
| Bereinigung der Alt-Suiten begründet, B11-Tests nicht abgeschwächt | PASS | — | Testbericht Kap. 3 (je Fall Begründung), Kap. 8.3 (Messmethode entschärft, „die Assertion wurde nicht abgeschwächt“); eigener Diff-Abgleich der drei fremden Testdateien gegen Baseline: nur testseitige Anpassungen an die neue Semantik „aktueller Lauf" (z. B. `test_output_view_f19_api.py:474-494`), keine Feldsemantik gelockert |
| Runde-2 Minor: full-Protokoll korrigiert | PASS | — | `docs/features/B11.md:251-276`: 1714 Tests, 2 Fehlschläge, beide am Baseline `b46b98d` im isolierten Klon nachgemessen (10 identische Verstoßorte beim Release-Test) — deckt sich mit der Koordinatorangabe; nicht eigenständig laufverifiziert |
| Runde-2 Minor: Nachbereitung getickett | PASS | — | `TICKETS.md:997-1009` („B11-Nachbereitung Steer-Zielprüfung auf den aktuellen Lauf begrenzen“) mit Akzeptanzkriterien; `docs/features/B11.md:296-300` verweist korrekt darauf |
| Runde-2 Minor: Schreibkosten akzeptiert und dokumentiert | PASS | `bin/vibe_runs.py:106-141,172-190` | `docs/features/B11.md:301-307` — bewusste Entscheidung mit Begründung und Größe (bis ~3,2 MiB je Ereignis im Grenzfall); Grenzfallgröße durch Budget-Tests gedeckt |
| Restfall geteilter opencode-Server ohne Sandbox: dokumentiert, getickett, vertretbar | PASS | `bin/vibe-run.sh:522,542-553` — Sandbox `on` erzwingt `--standalone` (gesamte Ausführung in der beendeten Prozessgruppe); `--server` nur bei Sandbox `off` und laufendem Gemeinschaftsserver; `.vibe/project.env:10` `SANDBOX="on"` (Voreinstellung abgedeckt) | `docs/features/B11.md:312-323` (OpenAPI v2.3.0, 139 Pfade, kein Cancel-Endpunkt für `session.prompt`) + `TICKETS.md:1011-1031` (Nachbereitungsticket mit Akzeptanzkriterien und erlaubten Nachweiswegen). Beurteilung: vertretbare dokumentierte Grenze, kein Blocker — die Ursache liegt außerhalb des Pakets (opencode-API), der Standardpfad (Sandbox) ist durch Prozessgruppen-Kill voll abgedeckt, und der Restfall ist mit echter Klarheit („nicht belegt", nicht „funktioniert") ausgewiesen statt behauptet. Nachweispflicht liegt beim Nachbereitungsticket |
| Importmanifest aktuell | PASS | `docs/import-manifest.json:794-805` (B11-Eintrag, Datum 2026-11-13, fünf Dateien, updated Größen/SHA-256 mit Begründung inkl. Runde-2-Nachtrag) | Datei gelesen; SHA-256-Werte selbst nicht nachgerechnet (keine Nicht-Git-Befehle erlaubt) |

## Findings

- [Minor] `docs/import-manifest.json` — Gesamtreformatierung ohne Begründung im B11-Eintrag
  - Evidence: Der Manifest-Diff zeigt 1116/1104 geänderte Zeilen; neben dem B11-Eintrag und den aktualisierten Prüfsummen wurde die gesamte Datei von 1- auf 2-Leerzeichen-Einrückung umformatiert (Inhalt sonst unverändert). Die Begründung im B11-Eintrag (`docs/import-manifest.json:804`) nennt nur die aktualisierten `files`-Hashes, nicht die Einrückungsänderung; die Runden 1 und 2 haben dies nicht beanstandet. Rein kosmetisch, JSON-Struktur und Einträge intakt.
  - Required fix: Optional — die Einrückung des Ausgangsstands beibehalten oder die Formatierung im B11-Eintrag mit begründen, um zukünftige Manifest-Diffs lesbar zu halten. Nicht blockierend.
  - Koordinatorvermerk: Umgesetzt — der B11-Eintrag begründet die
    2-Leerzeichen-Einrückung aus dem fortgeführten Stand des
    abgebrochenen Laufs (unveränderte JSON-Struktur).

## Verification

- Change set reviewed: Ausgangscommit `b46b98d` … uncommitteter Arbeitsbaum
  (`git status --short`: 11 geänderte/gelöschte + 6 neue B11-Dateien;
  TICKETS.md/FEEDBACK.md sind gitignorierte Arbeitsbaumeinträge und liegen
  im Arbeitsbaum vor — Zeilen 997-1031 bzw. 540-548). Vollständige Diffs
  gelesen: `bin/vibe-run.sh`, `bin/vibe_runs.py`, `bin/vibe-web.py`,
  `bin/web/app.js`, `bin/web/styles.css`, `docs/import-manifest.json`,
  alle drei fremden Testdateien; neue Dateien vollständig bzw.
  abschnittsweise gelesen (Stop-Suite inkl. `StopAgentGroupFallbackTest`
  vollständig, Stream-Relay, API-Suite, Browser-Suite, Runner-Fixtures).
- Git commands run by me: `git status --short`, `git log --oneline -3`
  (HEAD = `b46b98d`), `git diff HEAD --stat/--numstat/--name-only`,
  `git diff HEAD -- <Datei>` für alle Kern- und Testdateien.
- Checks with supplied output (vom Koordinator geliefert, von mir nicht
  eigenständig ausgeführt): B11-Unit 33 OK; Browser `test_b11_output_ui` +
  `test_f20_harness_ui` 18 OK; Regressionen
  (F25/F19-API/F19-Runner/B6/AP14-API/F24/AP14-capabilities/AP14-continue)
  92 OK; `verify.sh quick` Exit 0; `verify.sh full` 1714 Tests,
  2 Fehlschläge, beide am Baseline `b46b98d` im isolierten Klon identisch
  nachgemessen. Rotphasen: Testbericht Kap. 7.1 (6 Stamm-Stopp-Fälle mit
  Fehlerauszügen) und Kap. 8.3 (Fallback-Fall, 3-fach deterministisch
  rot) — beides Protokollauszüge, keine bloße Behauptung.
- Checks not independently run: alle Build-/Test-/Suitenläufe,
  `verify.sh` in beiden Stufen, SHA-256/Größenabgleich des Manifests,
  OpenAPI-Prüfung des opencode-Servers (139 Pfade), Branch-Name
  (`docs/features/B11.md:5` nennt
  `vibe/vibe-B11-1794584078598926007-2578957-11535` — Shell-Verweigerung;
  als einzige unverified Angabe markiert). Die Annahme „einziger
  Hintergrundauftrag" des `jobs -p`-Rückfalls habe ich statisch belegt
  (genau eine Backgrounding-Stelle, Preflight-Assistenz räumt über `wait`
  auf), nicht durch einen reproduzierten Lauf mit zwei gleichzeitigen
  Aufträgen.
- Important areas inspected: Prozessgruppen-/Trap-Umsetzung inkl.
  EXIT-Trap vor `run_agent_in`, Signal-Traps vor dem ersten Preflight,
  KILL-Eskalation; `stop_agent_group`-Rückfall und seine Vertragsfälle;
  Erfassungs-/Tail-/Versuchskontextlogik in `vibe_runs.py` inkl.
  F25-„zuletzt gewinnt"; API-Filter (aktueller Lauf, 4-KiB-Tail,
  `order=asc`, fail-open-Zeitfilter); neue `outputView` (Moduswechsel
  agent/legacy, verify-Pinning, Ziel-select, Fortsetzen, kein
  XSS-Vektor); Doku-Widerspruchsfreiheit (Ziel, Abgrenzung, Tests,
  Prüfungen, Grenzen — inkl. der neuen Abschnitte Fortsetzung und
  Grenzen); TICKETS.md-Neueinträge; FEEDBACK.md B11-Originaltext.
- Remaining risks: Der Restfall „geteilter opencode-Server ohne Sandbox"
  bleibt bewusst offen (verhaltensmäßig unbelegt, nicht API-steuerbar) —
  abgedeckt durch Nachbereitungsticket `TICKETS.md:1011`; Abgleich, ob
  das `bash`-Verhalten bei Signaltod (EXIT-Trap, Testbericht Kap. 7.2
  B1a) auf anderen Plattform-/bash-Versionen genauso ausfällt, ist
  plattformabhängig. Manifest-Prüfsummen unabhängig ungeprüft.
  Trilium-Dokumentation und Commit des Pakets liegen beim Koordinator
  (nach diesem PASS abzuschließen); der Abschluss darf gemäß AGENTS erst
  nach dieser Review-Antwort erfolgen.

## Verdict

PASS
