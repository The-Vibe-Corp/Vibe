# Review V-004 — Runde 3

Reviewer: `code-reviewer_glm`
Geprüfter Stand: finaler Arbeitsbaum gegen Ausgangscommit `b471b08` (nach Schließung der beiden Minor-Befunde aus Runde 2)
Verdikt: PASS (1 Minor)

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

`VERDICT: PASS`

Both round-2 findings confirmed independently closed; no new Critical/High/Medium findings.

## Akzeptanzkriterien (bestätigt, unverändert aus Runde 1/2)

| Kriterium | Status | Implementierung (file:line) | Test (file:method) / Nachweis |
|---|---|---|---|
| Nur Loopback | PASS | `bin/vibe-web.py:26-46` (`loopback_bind`, Abbruch vor Token-Write) | `tests/unit/test_web_api_security.py:467-…` (`LoopbackBindTest`); Positionsangabe je Runde-1/2-Befund |
| Nicht autorisierte Schreibzugriffe abgelehnt | PASS | `bin/vibe-web.py:203-212` (`_authorized`, Bytes-Vergleich — von mir per grep bestätigt), `:214-227` (`_guard`) | `AuthorizationTest`, 10 Tests, `tests/unit/test_web_api_security.py:217-342` |
| Health identifiziert vibe und Instanz ohne Geheimnisse | PASS | `bin/vibe-web.py:264-274` (`_health`) | `HealthTest.test_health_identifies_vibe_and_instance_without_secrets` (`:179-202`) |
| Keine Tokens in Logs | PASS | `bin/vibe-web.py:182-189` (`log_request` ohne Query), `redact` `:57-59` | `LoggingTest.test_token_never_appears_in_server_logs` (`:449-…`) |
| Strukturierte Fehler / Requestlimits | PASS | `bin/vibe-web.py:89-94, 214-227, 233-…` | `RequestValidationTest` (5 Tests, `tests/unit/test_web_api_security.py:344-…`), `ConcurrencyTest` (2 Tests) |
| Ticket-Tests: fehlendes/falsches Token, fremder Origin/Host, ungültiges JSON, übergroße Requests, parallele Anfragen | PASS | — | Alle in `tests/unit/test_web_api_security.py` vorhanden — 22 `test_`-Methoden von mir gezählt (grep), Konsistent 22 Modul / 283 Unit / 297 erkannt in `docs/features/V-004.md:25,138,170,187` und Trilium-Notiz; Runs nur vom Einreicher berichtet, nicht von mir ausgeführt |

## Findings

- [Minor] `docs/reviews/V-004-review-2.md:33` vs. `docs/features/V-004.md:138` — identische Laufzeitangabe bei unterscheidlicher Testzahl (nicht prüfbar)
  - Evidence: Der Runde-2-Dokumentation folgend berichtet sie für 21 Tests eine Laufzeit von exakt 1.355s; das finale `docs/features/V-004.md` nennt für 22 Tests ebenfalls exakt 1.355s. Da der hinzugekommene Stream-Test einzeln gemessen 0.054s benötigt, wäre eine leicht höhere Wert expected und eine 3-Dezimal-Kollision auffällig möglich — eine Transkripition in einem der beiden Zitate könnte ungenau sein. Diese Laufzeitangaben sind reine Berichte; weder implementiert noch bestätigt, Thema der korrekten Testzustände.
  - Required fix: Kein Codefix. Bei späteren Nachweisen Laufzeiten unveresdrückt nummerisch weit auseinander kürzen; die Substatz (Rot→Grün) ist durch die getrennten Rot-Nachweise belegt.

Keine Critical/High/Medium-Befunde.

## Fix-Bestätigung aus Runde 2

1. **Trilium-Notiz `VrwC3K1wD5hI` — geschlossen.** Unabhängig per MCP `get_note` verifiziert: Titel „V-004 Web-API absichern und Health-Endpunkt ergänzen“ (Parent `IjRpjYJTtqam`), Inhalt nennt 22 Modul-Tests, 283 Unit-Tests, 297 erkannte Tests, den UTF-8-Bytes-Vergleich als Fix (`compare_digest` auf `str` wirft bei Nicht-ASCII `TypeError`) mit `RemoteDisconnected`-Roturnal, strukturierten 403-Verhalten für Header- und `/api/stream`-Query-Pfad sowie die neue Manifestprüfung `6c836dbabce8…`/68788 Bytes. `utcDateModified` 2026-10-26 19:04:18 UTC. Übereinstimmend mit `docs/features/V-004.md` und `docs/import-manifest.json:32-33` (Bin/vibe-web.py-Eintrag im Diff-Kontext, Zeilen 32-33).
2. **Neuer Nicht-ASCII-Stream-Test — geschlossen.** `tests/unit/test_web_api_security.py:253-264` (auf Disk verifiziert, nicht nur im Diff): `GET /api/stream?name=proj&kind=run&t=<quote('tökén')>` ohne Header-Token, Assertion 403, `error.code == "unauthorized"`, Token nicht im Body. Implementierungsdeckung: `bin/vibe-web.py:203-212` (`_authorized`, `.encode("utf-8")`-Bytes-Vergleich), `:281` (`allow_query` nur für `/api/stream`) — beide durch grep bestätigt.

##重大项目 Kategorien-Check (Neuissues durch die Note-Update/Importe)

- Der Trilium-Notizeninhalt ist vollständig, korrekt und widerspricht der lokalen Dokumentation und dem Manifest.
- Der neue Test: nutzt den vorhandenen Fixture-`request`-Pfad, verändert nichts anderes; kein Skip, keine assertionlosen Bodies; der einzige `pass` (`tests/unit/test_web_api_security.py:82`) ist die `OSError`-Verbindungsrestrafe der Fixture — kein Test-Integrity-Problem.
- Testintegrität: 22 Tests gezählt, assertions/StateChecks okay; `git diff` zeigt keine entfernten.together.Dateien (keine Streichung vor der Testsuite und erwans).
- Untracked-Change-Set: `bin/vibe-web.py`, `docs/baseline.md`, `docs/import-manifest.json`, `docs/trilium-index.md` geändert; `docs/features/V-004.md`, `docs/reviews/V-004-review-{1,2}.md`, `tests/unit/test_web_api_security.py` neu — deckt sich mit dem vorgelegten Diff. Die drei PNG-Änderungen sind laut Paket vorbestehende fremde Änderungen und wurden nicht bewertet (beim Packages nicht mitkommit).

## Verification

- Change set reviewed: `b471b08..working tree` (`base` b471b08), inkl. vollständiger neuer Dateien aus `/tmp/opencode/v004-diff.md` und Disk-Abgleich der Kernstellen.
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git rev-parse HEAD`, `git branch --show-current`, `git diff b471b08 --stat` (weitere Nicht-Git-Shellbefehle wie `sha256sum`/`wc -c` wurden von der Umgebung verweigert).
- Checks with supplied output (alle vom Einreicher, nicht von mir ausgeführt): initiale Rotphase `Ran 19 tests … FAILED (failures=10, errors=10)`; Nicht-ASCII-Redo-Rot `RemoteDisconnected`/`FAILED (errors=1)`; final `Ran 22 tests in 1.355s OK`; Unit `Ran 283 tests … OK`; `bash scripts/verify.sh quick` → Exit 0 (26 Manifestdateien); `bash scripts/verify.sh full` → Exit 0, `OK: Tests erkannt: 297 (Minimum 1)`.
- Trilium-Notiz `VrwC3K1wD5hI` von mir unabhängig via MCP `get_note` geprüft (eine der beiden Fragen von Runde 2 also nicht glaubensbasiert, sondern verifiziert).
- Checks not independently run: alle Build-/Testläufe; die Manifest-Hash/Bytegröße von `bin/vibe-web.py` konnte ich nicht selbst nachrechnen (`sha256sum` verweigert) — Konsistenz nur belegt über den berichteten quick-Lauf und die inhaltliche Deckung zwischen Manifest, `docs/features/V-004.md` und Trilium-Notiz.
- Important areas inspected: `tests/unit/test_web_api_security.py` (22 Tests, insbesondere `:253-264`), `bin/vibe-web.py` `_authorized`/`allow_query` (`:203-212`, `:281`), `docs/features/V-004.md`, `docs/import-manifest.json`, `docs/trilium-index.md`, `docs/reviews/V-004-review-1.md`, `docs/reviews/V-004-review-2.md`, Trilium-Notiz per MCP.
- Remaining risks: Die fachlichen API-Routen bleiben bewusst ungetestet (im Paketumfang erklärt, Folgetickets V-005/V-009/V-012/V-013); alle Test- und Verify-Läufe nur berichtet; die drei PNG-Änderungen liegen weiterhin im Arbeitsbaum und dürfen beim Abschlusscommit nicht in das V-004-Paket gelangen (Runde-1-Festhaltung gilt).
