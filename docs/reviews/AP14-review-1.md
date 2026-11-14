# Review result

Reviewrunde 1 zum Arbeitspaket AP14; Arbeitsbaum
`vibe/vibe-AP14-1794504445407427942-147651-9932`, Basiscommit 9361689,
Datum 2026-11-12. Wörtlich übernommene Reviewantwort (unverändert).

## Summary
- Critical: 0
- High: 1
- Medium: 0
- Minor: 4
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Hauptagent jederzeit einsehbar (Panel dauerhaft vorhanden) | PASS | `bin/web/app.js:498-511` (sync: Hauptanzeige ohne Tabs, `fallbackToMain`), `bin/web/app.js:438-439` (`showMain`) | `tests/browser/test_ap14_output_ui.py:435` `MainPanelTest.test_main_agent_panel_is_always_present_even_without_subagents` (Prüfung auf „Hauptagent“ **und** Hauptmarker + JS-Fehlerfreiheit); Bericht Abschnitt a) |
| Laufende Subagenten live beobachtbar (eigene Panels, vollständige Ausgabe) | PASS | `bin/web/app.js:504,512-527` (Tabs nur für `status==='running'`), `bin/vibe-web.py:291-340` (500 Nachrichten, Text/„[Denken]“/„[Werkzeug]“, v2+Legacy, Nutzer übersprungen), Polling 2 s (`bin/web/app.js:186`) | `tests/browser/test_ap14_output_ui.py:456` `SubagentPanelsTest…`; `tests/unit/test_ap14_output_view_api.py:776-837` `LiveOutputTest` (3 Fälle); Bericht Abschnitt b) |
| Abgeschlossene Subagenten nicht aufbewahrt (Ansicht) | PASS | `bin/web/app.js:504` (Filter), `bin/web/app.js:521` (Tab/Pane-Entfernung) | `tests/browser/test_ap14_output_ui.py:479-499` (Panel verschwindet, Hauptpanel bleibt, Protokollkarte frei); Bericht Abschnitt b). Hinweis: Doku übertreibt den serverseitigen Anteil → Finding 2 |
| Continue in derselben Session (kein neuer Modell-Session-Start) | PASS | `bin/vibe-web.py:501-531` (`start_continue`), `bin/vibe:1961-1970,2080-2086` (Validierung + Export), `bin/vibe-run.sh:97-105,825-828,319` (`VIBE_CONTINUE_SESSION` → `RESUME_SESSION` → `--session`), Pi-Zweig `bin/vibe-run.sh:303-313` ohne `--session` | `tests/unit/test_ap14_output_view_api.py:673-758` (5 Fälle inkl. 403 ohne Token, aktiver Lauf, ohne Session, Pi), `tests/unit/test_ap14_runner_continue.py:195-501` (7 Fälle: CLI-Export, Kette, F25-Regression, Pi nie `--session`); Bericht Abschnitt d) |
| Anweisungen an Hauptagent UND jeden Subagenten | PASS | `bin/vibe-web.py:435-498` (`session`-Feld, Zielprüfung Haupt- oder erfasste Subagent-Session, Fremde abgelehnt), `bin/vibe-web.py:398-408` (Zeichenvalidierung+URL-Quoting), `bin/web/app.js:535-562` (Zielwahl/Beschriftung/POST) | `tests/unit/test_ap14_output_view_api.py:573-670` (6 Fälle, Beweis über aufgezeichnete `POST /api/session/<id>/prompt`), `tests/browser/test_ap14_output_ui.py:515-570` (2 Fälle); Bericht Abschnitt c) |
| Kompatibel mit jedem konfigurierbaren Harness | PASS | `bin/vibe_harness.py:71-87` (`supports()`, fail-closed für Unbekanntes), `bin/vibe-web.py:456,525` (Ablehnung bei Pi), `bin/vibe-run.sh:826` (Pi-Meldung) | `tests/unit/test_ap14_harness_capabilities.py:50-138` (5 Fälle inkl. Reinheit), `tests/browser/test_ap14_output_ui.py:618-666` (Pi sendet nie), `tests/unit/test_ap14_runner_continue.py:453-501` (Pi erhält nie `--session`); Bericht Abschnitt e) |
| Feature-Dokumentation vorhanden und zutreffend | FAIL | `docs/features/AP14.md` (vorhanden, weitgehend zutreffend) | Findings 2 und 3: zwei unzutreffende Behauptungen („serverseitig verworfen“, Fallzahl „80“) |

## Findings

- [High] `docs/reviews/AP14-test-agent-report.md:114-123,137` — Fehlender Rotphasen-/Failing-first-Nachweis für alle 34 neuen AP14-Tests
  - Evidence: Der Bericht gibt selbst an: „Einen beobachtbaren Rotphasen-Nachweis gibt es für diesen Lauf nicht“ (Zeilen 114-118, Grenze Zeile 137). Alle gelieferten Prüfergebnisse sind ausschließlich Grün mit der fertig implementierten Arbeitskopie; ein Nachweis, dass die Tests ohne die AP14-Änderung fehlschlagen, fehlt. Damit ist nicht belegt, dass die Tests das AP14-Verhalten überhaupt prüfen und nicht bereits gegen den Ausgangsstand grün wären.
  - Required fix: Rotphase nachliefern (keine Codeänderung): in einem temporären, isolierten Checkout/Worktree bei Ausgangscommit 9361689 die vier AP14-Testdateien einsetzen, die Suiten ausführen und die erwarteten Fehlschläge (fehlende `supports()`-Schicht, fehlender `/api/continue`-Endpunkt, fehlende Session-Validierung usw.) als Failing-first-Protokoll dokumentieren; den Nachweis im Testbericht ergänzen und anschließend erneut reviewen lassen.
- [Minor] `docs/features/AP14.md:32-33` (ebenso `docs/import-manifest.json:783`) — Falsche Behauptung „serverseitig verworfen“
  - Evidence: Beendete Subagenten werden nur aus der Tabliste gefiltert (`bin/web/app.js:504,521`). Serverseitig werden Einträge nicht verworfen: `bin/vibe_runs.py` kennt keine Entfernung von `subagents`-Einträgen (nur Anfügen, Zeilen 266/362/385/398; Zustandsdatei bleibt über Läufe hinweg bestehen), und die kompakte Subagenten-Übersicht listet beendete Einträge weiterhin. Die ticketgerechte UI-Anforderung ist erfüllt, die Dokumentation beschreibt aber ein nicht existierendes serverseitiges Verhalten.
  - Required fix: Formulierung in `docs/features/AP14.md` und `grund`-Text des Manifests korrigieren (z. B. „aus der Agentenauswahl entfernt; die Zustandsdatei behält erfasste Einträge weiter“).
- [Minor] `docs/features/AP14.md:144` — Fallzahl „80 Fälle“ stimmt nicht
  - Evidence: Summe der in derselben Datei (Tabelle Zeilen 128-136) und im Testbericht genannten Suiten: 5+14+7+8+16+19+5 = 74, nicht 80.
  - Required fix: Zahl auf die tatsächlich summierte Fallzahl korrigieren.
- [Minor] `bin/vibe-web.py:490-493` — Protokollmarker nennt bei zielgenauer Zustellung nicht das Ziel
  - Evidence: Bei Zustellung an eine Subagent-Session schreibt der Marker unverändert „Zusatzanweisung an den Agenten übermittelt“ ohne Ziel-Session/Agentnamen; die F19-Formulierung ist mit AP14-Multi-Target nun mehrdeutig (Nachvollziehbarkeit im Laufprotokoll).
  - Required fix: Marker um die Zielkennung (Session und/oder Agentenname) ergänzen; Dokumentation (`docs/features/AP14.md`, Schnittstellentabelle) entsprechend anpassen.
- [Minor] `docs/reviews/AP14-test-agent-report.md:105,128-131` — Persönlicher Cache-Pfad im Repository-Dokument
  - Evidence: Der Bericht nennt wiederholt den persönlichen Playwright-Cache-Pfad eines Nutzers (`/var/mnt/program_data/marc/cache/ms-playwright`), der laut AGENTS.md („Keine persönlichen Konfigurationen … ins Repository kopieren“) nicht ins Repository gehört; `docs/features/AP14.md:155-157` zeigt, dass der Umgebungsaspekt ohne den Pfad beschreibbar ist.
  - Required fix: Im Bericht den konkreten Pfad durch eine neutrale Beschreibung („lokal vorhandener Playwright-Browser-Cache via `PLAYWRIGHT_BROWSERS_PATH`“) ersetzen.

Keine Critical- oder Medium-Befunde. Die Browser-Testanpassung (`ignore_cleanup_errors=True`, `tests/browser/test_ap14_output_ui.py:146`) ist eine dokumentierte, assertionserhaltende Teardown-Ausnahme und kein Abschwächungsbefund.

## Verification
- Change set reviewed: `9361689..working tree` (8 geänderte Dateien per `git diff 9361689` vollständig gelesen; 6 neue unversionierte Dateien vollständig gelesen).
- Git commands run by me: `git status --short`, `git diff 9361689` (in drei Sichten: `bin/vibe`/`vibe-run.sh`/`vibe_harness.py`, `vibe-web.py`, `app.js`/`styles.css`/Doku).
- Checks with supplied output (vom Test-Agenten/Koordinator belegt, von mir nicht ausgeführt): AP14-Unit 26 OK, AP14-Browser 8 OK (mit `PLAYWRIGHT_BROWSERS_PATH`), Regressionen F25 16 / F19 19 / F24-Browser 5 OK, `bash scripts/verify.sh quick` Exit 0, `python3 scripts/check-import-manifest.py` OK (60 Dateien). Keine Abschwächung bestehender Tests feststellbar (keine F-Testdateien im Change set).
- Checks not independently run: alle Build-, Test-, Verify- und Manifest-Prüfungen; ich durfte und konnte keine Tests selbst ausführen.
- Important areas inspected: `bin/vibe-web.py` (steer/continue/subagent-output/Endpunktschutz, Zeilen 258-531, 770-839, 900-1019), `bin/vibe` (`cmd_run`-Validierung/Export, 1958-2086), `bin/vibe-run.sh` (`CONTINUE_SESSION`-Prüfung, `RESUME_SESSION`-Kette inkl. F25-Basisvergleich, Pi-Zweig), `bin/web/app.js` (Agent-Tabs, steerCard, Continue-Leiste, Polling), `bin/vibe_harness.py`, `bin/vibe_runs.py` (Subagentenpersistenz, Pi-Erfassung), alle vier AP14-Testdateien, Testbericht, Feature-Doku, compatibility.md, import-manifest.json, TICKETS.md (Zeile 923 bestätigt) und SPEC.md (keine speziellen Ausgabe-Anforderungen vorhanden).
- Remaining risks: (1) Fehlender Rotphasennachweis (Finding 1, High). (2) Trilium-Dokumentation ist im Change set nicht nachweisbar — laut AGENTS.md-Arbeitsablauf erst nach Reviewrunden Teil des Abschlusses; bis dahin bleibt das Paket unvollständig. (3) Continue prüft die erfasste Session nicht gegen den opencode-Server: Bei Harnesswechsel oder ungültiger Kennung schlägt der Lauf erst beim Start mit `--session` fehl; F25-Kette hält dann an der ungültigen Kennung fest (wiederherstellbar durch Neustart ohne Continue). (4) Die Herkunftserklärung der Tests ist ausschließlich durch den TESTER-Bericht belegt und von mir nicht unabhängig verifizierbar.
