# Review V-004 — Runde 2

Reviewer: `code-reviewer_glm`
Geprüfter Stand: Arbeitsbaum gegen Ausgangscommit `b471b08` inkl. Behebung des Minor-Befunds aus Runde 1
Verdikt: PASS (2 Minor)

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS (Bestätigung der Runde-1-Fixes; keine blockierenden Befunde)

`VERDICT: PASS`

## Fix-Bestätigung (Runde 1, Minor: Nicht-ASCII-Token)
- **Fix korrekt und vollständig:** `bin/vibe-web.py:203-212` — `_authorized()` liest zuerst `X-Token` (Header), bei `allow_query=True` (nur `/api/stream`, siehe `do_GET`, `bin/vibe-web.py:281`) das Query-Parameter-Token; beides läuft **durch dieselbe** Bytes-Vergleichsstelle. Leerer Wert → `False` (`:207-208`), der Vergleich als UTF-8-Bytes (`:212`) kann nicht mehr werfen: Headerwerte kommen aus der Standardbibliothek als latin-1-decodierter `str` (jede Codepage 0x00–0xFF ist UTF-8-enkodierbar), `TOKEN` ist ASCII. `/api/stream` ist damit, auch ohne eigenen neuen Test für exakt diesen Pfad, strukturell abgedeckt — Tests für Query-Token-Ablehnung existieren separat (`test_token_in_query_is_not_accepted_for_normal_reads`, `tests/unit/test_web_api_security.py:257-262`).
- **Keine neuen Fehlerpfade:** Vor `compare_digest` gibt es nur `.encode("utf-8")` auf Werten, die immer enkodierbar sind; `parse_qs` decodiert UTF-8 mit `errors="replace"`, erzeugt also nie Enkodierfehler. Fail-closed bleibt erhalten (leerer/enkodierfehlerfreier Pfad → `False` → strukturierte `403`).
- **Test ist echt:** `test_write_with_non_ascii_token_is_rejected_with_structured_error` (`tests/unit/test_web_api_security.py:241-250`) sendet `X-Token: tökén` (latin-1-fähig, erreicht also den Server) und prüft über `assert_rejected_without_effect` (`:217-224`) Status 403, `error.code == "unauthorized"`, Nonempty-Meldung, Token nicht im Body und **keine Zustandsänderung** (Pause-Flag fehlt). Ohne Fix wirft `compare_digest("tökén", TOKEN)` `TypeError`, weil der eine Operand Nicht-ASCII-`str` ist; der Aufruf liegt in `do_POST` (`bin/vibe-web.py:308`) außerhalb des try-Blocks → Verbindungsabbruch ohne Antwort. Genau das deckt der berichtete Rote-Befund (`http.client.RemoteDisconnected`, `FAILED (errors=1)`) ab; der Ablauf ist mechanisch nachvollziehbar, nicht nur behauptet.

## Akzeptanzkriterien
| Kriterium | Status | Implementation (file:line) | Test (file:method) / Nachweis |
|---|---|---|---|
| Nur Loopback | PASS | `bin/vibe-web.py:20-35` (`loopback_bind`, Abbruch vor Tokenwurf), `:801` (`ThreadingHTTPServer((BIND, PORT))`) | `test_web_api_security.py:452-480` (`VIBE_UI_BIND=0.0.0.0` → Exit ≠ 0, „Loopback“, keine `web.token`); Lauf laut Bericht exit 0 |
| Nicht autorisierte Schreibzugriffe abgelehnt | PASS | `bin/vibe-web.py:203-212` (`_authorized`, jetzt Bytes-Vergleich), `:214-227` (`_guard`: Host + Origin + Sec-Fetch-Site) | `AuthorizationTest` (10 Tests, `:226-326`) inkl. neuem Nicht-ASCII-Test; Gegenprobe `:316-326` (200 bei korrektem Token/Origin) |
| Health identifiziert vibe und Instanz ohne Geheimnisse | PASS | `bin/vibe-web.py:264-274` (`_health`: `app`, `instance`, `bind`, `port`, `pid`, `started`), `:40` (instanzstabil) | `HealthTest.test_health_identifies_vibe_and_instance_without_secrets` (`:178-202`; Instanzkennung stabil, kein Token/Wort „token“ im Body) |
| Keine Tokens in Logs | PASS | `bin/vibe-web.py:182-189` (`log_request` ohne Query-String), `:57-59`, `:198-201` (`redact`) | `LoggingTest.test_token_never_appears_in_server_logs` (`:435-449`; Log enthält Pfad, aber weder Token noch `t=`) |
| Strukturierte Fehler | PASS | `bin/vibe-web.py:89-94, 198-201, 229-262` (RequestError 400/411/413/415 mit `error.code`) | `RequestValidationTest` (5 Tests, `:330-390`) |
| Ticket-Tests: fehlendes/falsches Token, fremder Origin/Host, ungültiges JSON, übergroße Requests, parallele Anfragen | PASS | — | Alle Present in `test_web_api_security.py` (21 Tests, gezählt: 2 Health, 10 Authorization, 5 RequestValidation, 2 Concurrency, 1 Logging, 1 LoopbackBind); Rote Phase `Ran 19 tests … FAILED (failures=10, errors=10)` und Grün `Ran 21 tests in 1.355s OK` vom Einreicher berichtet, nicht von mir erneut ausgeführt |

## Findings
- [Minor] `docs/trilium-index.md:12` / Trilium-Notiz `VrwC3K1wD5hI` — Trilium-Dokumentation noch auf dem Runde-1-Stand
  - Evidence: Die Notiz „V-004 Web-API absichern und Health-Endpunkt ergänzen“ (Existenz von mir unabhängig verifiziert: Titel, Parent `IjRpjYJTtqam`) nennt noch `Ran 20 tests OK`, `Ran 280 tests OK`, `294 Tests erkannt` und kennt den Runde-1-Minor-Fix nicht; der finale Stand ist 21/282/296 (so auch `docs/features/V-004.md:137-189`). Die Notiz selbst ist korrekt und vorhanden — nur der Delta der Fixrunde fehlt.
  - Required fix: Vom(predictions,) Implementation übernimmt vor dem Abschlusscommit die Notiz aktualisieren: aktuelle Testzahlen (21 Modultests, 282 Unit, 296 erkannt Review-basiert) und den Runde-1-Fix (Bytes-Vergleich des Tokens, strukturierter 403) eintragen; danach verify.sh quick erneut laufen lassen und den aktualisierten Notizstand verifizieren. Keine Codeänderung nötig.
- [Minor] `tests/unit/test_web_api_security.py:241-250` — Nicht-ASCII-Regression nur über den Header-Pfad getestet
  - Evidence: Derselbe Fehlervertrag gilt auch für das Query-Token von `/api/stream` (`bin/vibe-web.py:281`) und wird vom Fix abgedeckt, aber es gibt keinen Test, der ein nicht-ASCII-`t` am Stream-Endpunkt gegen strukturierter 403 prüft. Das Runde-1-Required-fix sprach nur von „einem Test mit Nicht-ASCII-Headerwert“, dieser ist vorhanden.
  - Required fix (optional, nach PASS-Schluss erst mit neuem Review): ergänzender Test mit `?t=<nicht-ascii>` gegen 403 — vorzubehalten als Folgepatch; blockiert nicht.

Keine Critical/High/Medium-Befunde.

## Verification (verifiziere)
- Change set reviewed: `b471b08..working tree`充电 — Umfang bestätigt via `git diff b471b08 --stat` (bin/vibe-web.py +216/…) und vollständige Lektüre der neuen Dateien; der vorgelegte diff `/tmp/opencode/v004-diff.md` stimmt mit dem当前 Arbeitsbaum überein (enthält bereits den Bytes-Fix und den neuen Test).
- Git commands run by me: `git log --oneline -5`, `git status --short`, `git diff b471b08 --stat`, `git diff b471b08 -- docs/trilium-index.md docs/baseline.md`, `git rev-parse --show-object-format` (weitere Shellzugriffe wurden von der Umgebung verweigert).
- Checks with supplied output (vom Einreicher, nicht von mir ausgeführt): `bash scripts/verify.sh quick` → Exit 0 (26 Manifest-Dateien OK, Syntax OK, keine Geheimnisse); `bash scripts/verify.sh full` → Exit 0 (282 Unit OK, 14 Browser OK, „Tests erkannt: 296 (Minimum 1)“); Rote/Grüne Phasen wie im Abschnitt TDD evidence angegeben.
- Checks not independently run: alle Build-/Testläufe; die Manifest-Prüfsumme/Bytegröße von `bin/vibe-web.py` konnte ich nicht selbst nachrechnen (Repository ist SHA-1-basiert, `sha256sum` war nicht erlaubt) — belegt allein über den berichteten quick-Lauf.
- Important areas inspected: `bin/vibe-web.py` vollständig (insbesondere `_authorized` `:203-212`, `do_GET`/`do_POST`-Guard-Reihenfolge `:276-308`, `_health` `:264-274`, `log_request` `:182-189`, Serverstart `:801-805`), `tests/unit/test_web_api_security.py` vollständig (keine Skips, keine assertionslosen Tests, echte Assertions mit Zustandschecks), `docs/features/V-004.md`, `docs/baseline.md` (Kap. 6/8/9), `docs/import-manifest.json` (V-004-Eintrag), `docs/trilium-index.md`, `docs/reviews/V-004-review-1.md`; Trilium-Notiz `VrwC3K1wD5hI` unabhängig per MCP verifiziert.
- Remaining risks: Trilium-Notiz leicht veraltet (Minor 1); fachliche API-Routen bleiben bewusst ungetestet (im Paketumfang dokumentiert, Folgetickets V-005/V-009/V-012/V-013); die drei geänderten PNG-Dateien sind laut Aufgabenstellung vom Paket ausgeschlossen und wurden von mir nicht bewertet — beim Commit nicht mitstagen, wie in Runde 1 bereits festgehalten.
