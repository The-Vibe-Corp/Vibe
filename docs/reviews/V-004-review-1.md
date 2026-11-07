# Review V-004 — Runde 1

Reviewer: `code-reviewer_glm`
Geprüfter Stand: Arbeitsbaum gegen Ausgangscommit `b471b08` (vor Behebung des Minor-Befunds)
Verdikt: PASS (1 Minor)

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: **PASS** (mit 1 Minor-Befund; keine blockierenden Beanstandungen)

`VERDICT: PASS`

## Akzeptanzkriterien

| Kriterium | Status | Implementierung (file:line) | Test / Nachweis |
|---|---|---|---|
| Nur Loopback | PASS | `bin/vibe-web.py:20-35` (`loopback_bind`, IPv4-Loopback-Pflicht, Abbruch mit Exitcode ≠ 0 vor Token-Write), `bin/vibe-web.py:512` (`ThreadingHTTPServer((BIND, PORT))`) | `tests/unit/test_web_api_security.py:442-467` (`test_a_non_loopback_bind_address_is_refused`: `0.0.0.0` → Exitcode ≠ 0, „Loopback“ in Ausgabe, keine `web.token`); graclos vom Lagerverfasser berichtet (finaler Stand), nicht von mir erneut ausgeführt |
| Nicht autorisierte Schreibzugriffe abgelehnt | PASS | `bin/vibe-web.py:203-207` (`_authorized`, Header-Token, `compare_digest`), `bin/vibe-web.py:209-222` (`_guard`: Host + Origin + Sec-Fetch-Site), `bin/vibe-web.py:300-307` (Guard → Token → Body-Lesung in dieser Reihenfolge) | `test_web_api_security.py:226-316` (fehlendes/falsches Token, fremder Origin inkl. fremdem Loopback-Port/portlos/https, fremder Host, `Sec-Fetch-Site: cross-site`; je Zuststands-Check `pause_flag`), Gegenprobe `:305-316` (gleicher Origin + Token → 200) |
| Health identifiziert vibe und Instanz ohne Geheimnisse | PASS | `bin/vibe-web.py:259-269` (`_health`: `app`, `instance`, `bind`, `port`, `pid`, `started`, `api:1`; Instanzkennung `secrets.token_hex(8)` in `:40`, stabil pro Prozess) | `test_web_api_security.py:178-202` (200 ohne Token, `app=="vibe"`, Instanzkennung stabil über zwei Aufrufe, Port/PID, Token nicht in Antwort, `"token"` void in Antwort) |
| Keine Tokens in Logs | PASS | `bin/vibe-web.py:182-189` (`log_request` schreibt nur Methode + Pfad ohne Query), `bin/vibe-web.py:57-59` (`redact`), `:198-201`, `:450` (Meldungen geredacted), `:205-206` (Query-Token nur noch `/api/stream`) | `test_web_api_security.py:424-439` (Log enthält `/api/projects`, aber weder Token noch `t=`) |
| Strukturierte Fehler | PASS | `bin/vibe-web.py:198-201` (`_error`: `ok:false`, `error.code`, `error.message`), `89-94` + `224-257` (`RequestError`: 415/411/400/413 mit Code) | `test_code`-Assertions in `test_web_api_security.py` in allen Fehler-Tests (z. B. `:319-329`, `:338-350`, `:351-366`, `:367-380`) |
| Ticket-Tests: fehlendes/falsches Token, fremder Origin/Host, ungültiges JSON, übergroße Requests, parallele Anfragen | PASS | — | 20 Tests vorhanden (`test_web_api_security.py:177-459`); Roter Stand `Ran 19 tests … FAILED (failures=10, errors=10)` und Grün `Ran 20 tests … OK` vom Lagerverfasser berichtet, nicht von mir erneut ausgeführt |

Ticketumfang geschlossen: Authentisierung, Host-/Origin-Prüfung, Requestlimmit (1 MiB, `bin/vibe-web.py:17,241-244`), Health. Erweiterte Frontend-Fehleranzeige (`bin/vibe-web.py:508`) gehört sachlich zu „strukturierte Fehler“ — kein Scope-Creep.

## Findings

- [Minor] `bin/vibe-web.py:203-207` — Nicht-ASCII-`X-Token`/`t` führt zu unsauberem Verbindungsabbruch statt strukturiertem Fehler
  - Evidence: `secrets.compare_digest` wirft bei str-Operanden mit Nicht-ASCII-Zeichen ein `TypeError`. `_authorized()` wird in `do_GET` (`:276`) und `do_POST` (`:303`) **außerhalb** der try-Blöcke aufgerufen, der Fehler eskaliert daher unbehandelt; der Client erhält keine Antwort (Verbindung bricht), statt des strukturierten `403 unauthorized`-Fehlers, und ein Traceback landet unstrukturiert auf stderr (bekanntermaßen ohne Token-Inhalt). Verhalten fail-closed — kein Auth-Bypass, keine Datenänderung — aber der Fehlervertrag („strukturierte Fehler“ aus dem Tokenpfad) schließt diese Eingabeklasse nicht. Gleiche Ursache gilt für das Query-Token bei `/api/stream` (`:206`).
  - Required fix: Vor `compare_digest` beide Seiten normalisieren (z. B. als `.encode("utf-8")`-Bytes vergleichen), sodass ein fehlerhaft formatierter Token zur strukturierten `403 unauthorized`-Antwort wird und nicht eskaliert; ergänzend einen Test mit Nicht-ASCII-Headerwert in `AuthorizationTest` aufnehmen. Keine Implementierungsänderung im Review — erst nach Bearbeitung erneut reviewen.

## Eigene Beobachtungen (ohne Befundcharakter)
- `LOOPBACK_HOSTS` enthält `::1`, gebunden werden kann nur IPv4 (`loopback_bind` lehnt ::1 ab) —被害frei, Host-Whitelist-Konsistenzstory dokumentiert.
- Query-Token-Restriktion nur für `/api/stream` ist eine begründete, dokumentierte Ausnahme (EventSource), Logs sind query-frei — baseliner Sicherheitsbefund Nr. 3 ist sauber adressiert (`docs/baseline.md:288-291`).
- Token-Datei wird bei Portkonflikt (gefundenen Bind) bereits vor dem Serverstart geschrieben — aber das war unveränderter Bestand vor V-004; die BIND-Weigerung wirft vor dem Write (Test belegt das).
- 3 geänderte PNG-Dateien (`F3-schreibrechte.png`, `F5-fritz.png`, `F7-sandbox.png`) sind nachweislich nicht Teil dieses Arbeitspakets; beim Commit nicht mitstageen („Commit enthält ausschließlich dieses Arbeitspaket“).

## Verification
- Change set reviewed: `b471b08..working tree` (git status: `bin/vibe-web.py`, `docs/baseline.md`, `docs/import-manifest.json`, `docs/trilium-index.md` geändert; `docs/features/V-004.md`, `tests/unit/test_web_api_security.py` neu — entspricht vollständig dem vorgelegten diff `/tmp/opencode/v004-diff.md`; PNG-Änderungen vom Paket ausdrücklich ausgeschlossen).
- Git commands run by me: `git status --short`, `git log --oneline -3`, `git rev-parse HEAD`, `git diff b471b08 --stat` (weitere Shellzugriffe wurden von der Umgebung verweigert).
- Checks with supplied output (alle vom Lagerverfasser berichtet, mit exakten Wortlauten im Paket und in `docs/features/V-004.md`): Roter Stand `Ran 19 tests … FAILED (failures=10, errors=10)`; Grün `Ran 20 tests … OK`; `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0 (unit 281 Tests OK, browser 14 Tests OK, 295 Tests erkannt).
- Checks not independently run:все build-/test-Läufe; ich konnte weder `verify.sh` noch die Testsuite selbst ausführen (reine Review-Rolle; Shellzugriff verweigert). Die Manifestkonsistenz (`sha256` von `bin/vibe-web.py` ↔ `docs/import-manifest.json`) konnte ich daher nicht selbst nachrechnen — sie ist über den reported `check-import-manifest`-Erfolg belegt, nicht über meinen eigenen Lauf.
- Wichtigste geprüfte Stellen: `bin/vibe-web.py:1-100` (Bind/sbin/Limits), `:179-307` (Guard/Auth/Limits/Health/Routing-Reihenfolge), `:300-460` (POST-Konvention inkl. `error.code:"rejected"` im `docs/features/V-004.md`-Format), `tests/unit/test_web_api_security.py` vollständig (20 Tests, 2+9+5+2+1+1; objektive Assertions, keine Skip/Deaktivierungsmarker, Asserts mit Zustands-Checks), `docs/features/V-004.md`, `docs/baseline.md` (Kapitel 6/8/9), `docs/import-manifest.json`, `docs/trilium-index.md`.
- Trilium-Dokumentation von mir unabhängig verifiziert: Notiz `VrwC3K1wD5hI` existiert unter Titel „V-004 Web-API absichern und Health-Endpunkt ergänzen“ (Parent `IjRpjYJTtqam`), Inhalt entspricht den berichteten Punkten — der Eintrag in `docs/trilium-index.md` ist korrekt.
- Remaining risks: Mindestens die 1 Minor-Befund (s. o.); die fachlichen API-Routen bleiben ausdrücklich ungetestet (dokumentiert in `docs/features/V-004.md:633-635`, Folgetickets V-005/V-009/V-012/V-013) — dies liegt im erklärten Paketumfang (Transport läuteteifier).
