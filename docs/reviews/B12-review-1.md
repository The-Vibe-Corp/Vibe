# Review — Arbeitspaket B12, Runde 1

Reviewer: unabhängiger code-reviewer (read-only)
Datum: 2026-11-13
Umfang: `git diff 6959136 -- bin/vibe_runs.py bin/vibe-web.py docs/import-manifest.json`; neue Dateien `tests/unit/test_b12_background_subagents.py`, `docs/reviews/B12-test-agent-report.md`, `docs/features/B12.md`; SPEC.md; Bericht wörtlich übernommen.

## Zusammenfassung

- Critical: 0
- High: 0
- Medium: 0
- Low: 1
- Info: 3
- Verdict: PASS

Der Fix ist minimal, korrekt im Ansatz und an den belegten Ursachestellen. Der Metadaten-Status wird nur bei bekannten Werten als Authorität verwendet (Pi/alt-opencode unverändert), die Wiederbelebung und die Dashboard-Herabstufung erfinden keinen Abschluss (ohne Kennwort/ohne Server kein Statuswechsel, kein HTTP-Aufruf). F25 „zuletzt gewinnt" bleibt für unbekannte Sessions erhalten. Die vom Test-Agenten vor der Implementierung geschriebene Suite deckt AK1–AK5 mit echten Verhaltensassertionen ab; Rot- und Grünphase sind im Test-Agenten-Bericht mit konkreter Ausgabe belegt. Der Reviewer konnte auf Grund der Berechtigung dieser Sitzung **keinerlei Shell-Kommandos außer Git-Lesebefehlen ausführen** — Green-Phase, Regressionen und verify.sh blieben Lieferanten-Nachweise (wörtlich unten zitiert) und wurden nicht unabhängig wiederholt.

## Befunde

- [Low] `tests/unit/test_b12_background_subagents.py:825-836` — AK4a-Test prüft nur den Status, nicht die übernommene `ended`-Zeit
  - Beleg: Der Test `test_dashboard_downgrades_running_entry_when_child_known_and_inactive` assertet ausschließlich `status == "completed"`; die Herabstufungslogik übernimmt `ended` nur bei Wahrheitsgehalt (`bin/vibe-web.py:413-414`). Diese Übernahme ist nicht abgedeckt — eine versehentliche Regression bei der `ended`-Übernahme würde grün durchlaufen.
  - Required fix (nicht blockierend): Beim nächsten Testkontakt durch den Test-Agenten ergänzen, dass bei bekannter, inaktiver Kind-Session `ended` der Live-Zeit entspricht (Attrappe liefert `time.updated = 1700000005000` → Sekundenwert).
- [Info] `tests/unit/test_b12_background_subagents.py` — Übergang „laufender Hintergrund-Eintrag → completed" über ein späteres task-Ereignis ist nicht getestet
  - Beleg: Getestet sind Erst-Erstellung mit Metadaten-`completed` (AK2), Wiederbelebung (AK3) und API-Herabstufung (AK4). Der Zustandspfad, bei dem opencode ≥ 2.3 den Werkzeug-Part nach Abschluss des Kindes aktualisiert (Metadaten-`completed` oder Statusfeld weg → Fallback auf `state.status`), ist nur Codepfad, nicht Testfall. Der Fallback ist per Codelesung korrekt (`bin/vibe_runs.py:423`, `446-455`); falls opencode die Metadaten dauerhaft auf `"running"` lässt, bleibt der Eintrag im Zustandsfile laufen und der Abschluss kommt nur über die API-Herabstufung bzw. die B11-Regel „kein aktiver Lauf → leere Liste" (`bin/vibe-web.py:862-866`) — beides dokumentiert (`docs/features/B12.md` §Grenzen). Kein Defekt, aber eine Lücke in der Fallabdeckung.
- [Info] `bin/vibe-web.py:406-414` — Herabstufung kann `completed` mit `ended=0` ergeben
  - Beleg: Ist `live["ended"]` falsy (Server liefert keinen Zeitstempel), bleibt das bestehende `ended=0` erhalten. Das ist ehrlich (kein erfundener Endzeitpunkt) und UI-neutral (die Ansicht listet nur `running`), aber inkonsistent zur Invariante „completed hat ended > 0" aus AK2 im Zustandsfile. Die API-Antwort wird nicht zurückgeschrieben, daher nur Hinweis.
- [Info] `docs/features/B12.md` (Umgebungshinweis) — erster Regressionlauf überschrieb `/var/mnt/data/…/VibeCode/_logs/web.token` (32 Bytes) des geteilten Runtime-Ordners
  - Beleg: Vom Koordinator selbst offen gelegt; kein Dashboard-Prozess liest diese Datei laut Angabe, weitere Läufe mit `env -u VIBE*`. Prozessbeobachtung, keine Codeänderung nötig; die Regel „Keine produktiven HOME-/VIBE-Konfigurationen in Tests" wurde danach eingehalten.

## Ticket vs. SPEC

- FEEDBACK.md B12 (Bug „Subagenten in Ausgabe nicht sichtbar") ist eindeutig; der genannte Screenshot `docs/Bildschirmfoto_20261113_172912.png` fehlt tatsächlich (per Glob verifiziert) — das dokumentiert `docs/features/B12.md` offen, die Ticket-Wortlage trägt den Beleg. Kein Widerspruch.
- SPEC.md („Agentenläufe und Prüfungen", Laufen/beobachten/anhängen) verlangt die Beobachtbarkeit; der Fix dient genau dem. Kein Scope-Übergriff: `bin/web/app.js` ist unangetastet (Git-Status), die B11-Semantik „beendete Subagenten verschwinden" bleibt. KISS/Clean Code: +47 Zeilen in `vibe_runs.py`, +9 in `vibe-web.py`, B12:-Kommentare im Hausstil, keine spekulativen Abstraktionen. Manifest (`docs/import-manifest.json`) mit neuem aenderungen-Eintrag und aktualisierten Bytes/SHA-256 für beide geänderten Bin-Dateien; „stand" auf 2026-11-13. Fachliche Doku `docs/features/B12.md` neu angelegt.

## Akzeptanzkriterien

| Kriterium | Status | Implementierung (file:line) | Test / Beleg |
|---|---|---|---|
| AK1 Metadaten-Status Authorität, Eintrag running/ended=0, Hauptsession unverändert | PASS | `bin/vibe_runs.py:220-239, 419-423, 425-458` | Tests 1-3; Rotphase `'running' != 'completed'` (Bericht Kap. 4), Grünphase OK (geliefert) |
| AK2 Alt-Verhalten ohne Statusfeld/mit completed/unbekanntem Status unverändert | PASS | `bin/vibe_runs.py:236-238` (nur bekannte Werte), `423` (Fallback) | Tests 4-6; in Rotphase bereits grün (Regressionsschutz, Bericht Kap. 4) |
| AK3 Wiederbelebung abgeschlossener Einträge durch Kind-Ereignisse | PASS | `bin/vibe_runs.py:310-315` + `363-371` | Test 7; Rotphase `'running' != 'completed'` (Bericht Kap. 4) |
| AK4 Dashboard-Herabstufung (a/b/c) ohne Erfindung | PASS | `bin/vibe-web.py:406-414` | Tests 8-11; Rotphase `'completed' != 'running'` (Bericht Kap. 4); AK4c „kein HTTP-Aufruf" per Request-Protokoll der Attrappe |
| AK5 Protokollzeile zeigt wirksamen Status | PASS | `bin/vibe_runs.py:460` | Tests 1-2 (Zeile endet auf „— running", keine „— completed"-Zeile) |
| AK6 Regressionen | PASS (geliefert) | — | 137 Tests OK + verify quick Exit 0 + full 1725 Tests / 2 vorbestehende Fehlschläge (am Ausgangsstand identisch nachgemessen) — alles gelieferte Ausgaben, vom Reviewer nicht unabhängig ausgeführt |

Test-Integrität: Der neue Test stammt nachweislich (Bericht Kap. 1-4 mit wörtlicher Rotphasenausgabe) vom Test-Agenten und wurde vor der Implementierung rot belegt. Keine Skips, keine assertionslosen Tests, keine Assertionsabschwächung in bestehenden Suiten (Git-Diff über `tests/` ist leer; nur die neue ungetrackte Datei kam hinzu). Die korrigierte Stelle (Kap. 7) betraf ausschließlich die Struktur (Zustandsprüfung nach TemporaryDirectory-Cleanup); die fachlichen Assertionen entsprechen genau den im Bericht genannten drei Erwartungen, der neue Rotphasenlauf scheitert an der Ausgabeassertion aus dem richtigen Grund.

## Prüfergebnisse

Vom Reviewer ausgeführte Git-Lesebefehle: `git status --short`, `git log --oneline -5`, `git diff --stat 6959136`, `git diff 6959136 -- bin/vibe_runs.py`, `git diff 6959136 -- bin/vibe-web.py docs/import-manifest.json`, `git log -- docs/features/B12.md`, `git diff 6959136 --stat -- tests/`. Kompletter Diff und alle drei neuen Dateien vollständig gelesen.

Gelieferte Prüfergebnisse (Koordinator/Test-Agent, vom Reviewer **nicht** unabhängig ausgeführt — alle Nicht-Git-Kommandos wurden von der Sitzungsberechtigung abgelehnt):
- Rotphase: `Ran 11 tests … FAILED (failures=5)` am Ausgangsstand 6959136, 5 Fälle an den Fixstellen; korrigierter Stream-Test erneut rot am Ausgangsstand (Bericht Kap. 7).
- Grünphase: `PYTHONDONTWRITEBYTECODE=1 env -u VIBE_RUNTIME python3 -m unittest tests.unit.test_b12_background_subagents -v` → `Ran 11 tests … OK`.
- Regressionen: 6 Suiten → `Ran 137 tests … OK`.
- `bash scripts/verify.sh quick` → OK, Exit 0; `env -u TMPDIR bash scripts/verify.sh full` → `Ran 1725 tests, FAILED (failures=2)`; beide Fälle am Ausgangsstand identisch fehlgeschlagen (isolierte Basiskopie) → vorbestehend. Der Reviewer hat die Regelextraktion gelesen (`tests/unit/test_release.py:315-347`, `scripts/build-release.py:73,199-211`): die neuen Dateien enthalten keine `/home|/Users/<name>`-Pfade und keine Geheimniswerte, schaffen also keine neuen Verletzungen dieses vorbestehenden Fehlschlags.

## Nicht unabhängig geprüft

- Alle Test- und verify-Ausführungen (siehe oben); SHA-256/Bytegrößen im Manifest nicht selbst nachgerechnet (nur Konsistenz des Diffs geprüft).
- Aussage „opencode ≥ 2.3 meldet Metadaten-Status running" beruht auf der Binäranalyse des Koordinators, nicht auf eigener Binärprüfung — Verhalten aber testseitig und fallbackseitig so abgesichert, dass auch abweichende Formen keinen Schaden anrichten (unbekannter Status → `state.status`).

## Verbleibende Risiken

- Stale Metadaten (`status:"running"` ohne späteres Abschlussereignis) halten den Zustandsfile-Eintrag bis zum Laufende laufend; wirksam abgefangen durch API-Herabstufung (geteilter Server) bzw. B11-Regel (Sandbox), dokumentiert, nicht blockierend.
- Kurzzeitiges Flackern (completed↔running) zwischen Polls ist theoretisch möglich, wenn `/api/session/active` zwischen zwei Aufrufen wechselt; spekulativ, ohne Beleg.
- Verbleibende Arbeiten bis Abschluss: Trilium-Dokumentation, Commit, Ticket-Abhaken — obliegt dem Koordinator gemäß AGENTS.md-Arbeitsablauf.
