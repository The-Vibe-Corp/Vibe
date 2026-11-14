# Review B7 — Runde 1 (2026-11-10)

Unveränderte Abschrift der Reviewer- (code-reviewer-) Antwort auf das Arbeitspaket B7
(Branch vibe/vibe-B7-1794295794403437735-1660139-21935, Ausgangscommit 5abce28, Umsetzungsstand uncommitted).
Grobe Modellartefakte (Zeichenumerrierungen, zusammengequetschte Wörter) bleiben bewusst unverändert.

---

# Review result

## Summary
- Critical: 0
- High: 1
- Medium: 0
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Auth über die UI (GitHub-Empfehlung: PAT) | PASS (mit Vorbehalt: Nachweise reportet) | bin/web/app.js:621–676 (Auth-Block, Passwortfeld, Token hinterlegen/entfernen), bin/vibe-web.py:743–752 (token.save/token.clear), bin/vibe_github.py:87–152 (Speicher), bin/vibe:1127–1139 (CLI getpass) | tests/browser/test_b7_github_auth_ui.py (Test 32, 33, 36), tests/unit/test_b7_github_auth.py:TokenRoutesWebTest (28–31) — gründe Läufe nur reportet (Unit 31 OK, Browser 6 OK), nicht von mir gestartet |
| Fehler dauerhaft sichtbar (Fehlerbox statt Toast) | PASS (Nachweis reportet) | bin/web/app.js:612–616 (errBox + setErr in jedem Pfad), setErr bei issues/import/pr:659, 664, 667 | Browser-Tests 34, 35 (`.bad` sichtbar nach ≥ 2,2 s) — reportet |
| Fehlerklassifikation mit Anweisungstext | PASS (Nachweis reportet) | bin/vibe_github.py:307–324 (_auth_guidance), 518, 530, 542 | Unit-Tests 23–27 (je fetch/pull/push), Browser-Test 35 — reportet |
| Token-Geheimhaltung (argv/Logs/Konfig/Antworten/Repos) | PASS (Nachweis reportet) | bin/vibe_github.py:92–125, 292–304 (GIT_CONFIG_* + ENV, nie argv), 155–164 (REST-Scoping), 74–85 (VIBE_STATE außerhalb Git-Repos) | Unit 8–14, 18, 22, 28–31; echtes Leak-Probe gegen 127.0.0.1 in Unit 14; Browser 33, 36, 37 — reportet |
| Umgebung > gespeichert konsistent in Git und REST | PASS (Nachweis reportet) | bin/vibe_github.py:279 (`token_from_env() or read_stored_token()`), 155–164 (token_for_rest:环境 zuerst) | Unit 11, 17, 19 — reportet |
| Kein Cache für Geheimnisse/SPEC-Caching-Regel | PASS | bin/vibe_github.py:128–135 (Dateilesen je Aufruf, kein Cache); kein neuer Modulzustand | — |
| ManIFEST SHA+Bytes für alle 5 Quelldateien | PASS | docs/import-manifest.json:28–29, 38–39, 48–49, 103–104, 113–114 + B7-Eintrag:917–931 | scripts/verify.sh quick EXIT 0 (reportet); Hashwerte separat von mir nicht nachgerechnet (shell nur für git-Lesebefehle freigegeben) |
| verify.sh full grün | NOT VERIFIED | — | Ergebnis zu Reviewzeitpunkt nicht vorgelegt (lief/nachlaufend laut Angabe); AGENTS verlangt quick **und** full verbindlich |
| Trilium-Dokumentation | FAIL | — | Tatsächlich geprüft: Notiz `RTYec92LsBSL` („AP6 Vorbereitung für github Repo") enthält **keine** B7-Ergänzung (Suchmuster B7: 0 Treffer; wie gelesener Zustand, last modified 2026-11-09); keine separate B7-Notiz im Projektordner „vibe" (67 Kinderkontrollnotizen gelesen) |

## Findings
- [High] `docs/features/B7.md:156–159` — Trilium-Sync als erledigt behauptet, ist aber nicht vorhanden
  - Evidence: B7.md behauptet „Ergänzung der AP6-Notiz `RTYec92LsBSL` … B7-Änderung, Prüfnachweise und Commit". Die Notiz auf dem Trilium-Server (Gelesen-Zustand,THIS review) enthält keinen B7-Verweis (Suchmuster B7: 0 Treffer, `utcDateModified` 2026-11-09 18:30, also vor dem🎫 Arbeitspaket); es existiert auch keine separate B7-Notiz. AGENTS (Arbeitsablauf 7 / Definition of Done) fordert die Trilium-Dokumentation tatsächlich durchzuführen und verbietet, eine lokale Datei als angeblich erfolgte Trilium-Dokumentation auszugeben. Dies ist eine Nachweisbehauptung, die der Zielstate widerspricht → blockiert den Abschluss.
  - Required fix: B7-Änderung, Entscheidungen und Prüfnachweis tatsächlich über den Trilium-MCP-Zugang dokumentieren (Ergänzung der AP6-Notiz oder eigenes B7-Blatt im Projektordner „vibe/Features"), erfolgreiches Schreiben lesend verifizieren und die Prüfnachweis-Lücke (verify.sh full) und den letzten Reviewzustand erst dann berichten, wenn alles vorliegt. B7.md xt erst danach die korrekte Notiz referenzieren.
- [Minor] `bin/vibe_github.py:271` — Tippfehler „Umgebungs-Konfigpur"
  - Evidence: beschädigtes Wort im fachl. Docstring, erschwert die Auffindbarkeit.
  - Required fix: Doku korrigieren.
- [Minor] `docs/features/B7.md:74–75` — abgebrochene (doppelte) Satzfragment im Änderungsabschnitt
  - Evidence: nach dem regulären Klassifikationsabsatz steht unvermittelt „Karten- und CLI-Meldungen, die ein Auth-Bild enthalten (" ohne Inhalt → Redundanz/Schräglage in der Fachdokumentation.
  - Required fix: Fragment entfernen bzw. mit dem folgenen Absatz zusammenführen.
- [Minor] `bin/web/app.js:640, 644` — setAuth nach Token-Aktionen miz jemandem statisch
  - Evidence: nach token.save wird `setAuth('gespeichert')` und nach token.clear `setAuth('')` hardcoded statt` die in `r.github.auth` (bzw. `r.auth`) mitgelieferte tatsächliche Quelle zu verwenden. Wenn im Dashboard ein Umgebungstoken (GITHUB_TOKEN/GH_TOKEN) gesetzt ist, zeigt die Karte nach Speichern fälschlich „gespeichert" bzw. nach Entfernen fälschlich „Kein Token hinterlegt". Die Tests prüfen mit gereinigter Server-Umgebung und schlagen deswegen nicht.
  - Required fix: UI bitte den Server-Status aus der tatsächlich zurückgegebenen `auth`-Struktur brauchen; die Tests werden vom Test-Agenten ergänzt, ggf. Umgebungstoken-Fall.

## Verification
- Change set reviewed: `5abce28..working tree` (git diff 5abce28 -- bin/ docs/import-manifest.json); neue Dateien vollständig gelesen: docs/features/B7.md, docs/reviews/B7-test-agent-report.md, tests/unit/test_b7_github_auth.py (978 Zeilen), tests/browser/test_b7_github_auth_ui.py (582 Zeilen). `git status --short` bestätigt genau die genannten 6 modifizierten und 4 neuen Dateien, keine fremden/bestehenden Änderungen.
- Git commands run by me: `git status --short`, `git diff --stat 5abce28 -- bin/ docs/import-manifest.json`, `git diff 5abce28 -- bin/vibe docs/import-manifest.json`, `git diff 5abce28 -- bin/vibe_github.py bin/vibe-web.py bin/vibe_services.py bin/web/app.js`.
- Checks with supplied output (vom Coding-/Test-Agenten reportet, von mir nicht ausgeführt): unittest test_b7_github_auth.py 31 OK; test_b7_github_auth_ui.py 6 OK; Regressionen (test_ap06_github 54 OK, test_web_api_security 22 OK, Browser AP06 9 OK); verify.sh quick EXIT 0. Rotphase laut B7-test-agent-report.md §5 (Unit 3 Failures/32 Errors, Browser 3 Failures/4 Errors) dokumentiert.
- Checks not independently run: alle Build- und Testläufe, sha256-Nachrechnung der ManIFEST-Werte (shell nur für git-Lesebefehle zugelassen), verify.sh full (Ergebnis nicht vorgelegt). Die byte-identische Wiederherstellung der gelöschten Testdateien nach dem git-stash-Zyklus ist nach Git-Status indirekt plausibel (nur die vier erwarteten Test-/Doku-Dateien als unveränderte Ursache; inhaltlich vollständig, Assertions keine Abschwächung ersichtlich), aber nicht beweisbar.
- Additional independent check: Trilium-Zugriff immer noch möglich — Notiz `RTYec92LsBSL` und der Elternordner (67 Kinder) wurden gelesen: keine B7-Dokumentation vorhanden (Grundlage des High-find).
- Important areas inspected: Token-Speicher/Rechte (best effort, atomar via os.replace, FUSE-Lüge vermeidend), Credential-Injection (GIT_CONFIG_* URL-scoped, Token nur in der Prozessumgebung, nie argv/Konfigdatei/Log), REST-Scoping (gespeicherter Token ausschließlich api.github.com; Umgebungstoken Scenet wie bisher), Fehlerklassifikation inkl. „Zugangsdaten"-Doppelungs-Schutz, Web-API endpunkte (X-Token-Pflicht bleibt, Geheimnis-freie Antworten), Karte app.js (textContent/createElement → kein XSS aus GitHub-Adapter-Texten), CLI getpass-Pfad (Token nie als Argument), Manifest-B7-Eintrag, Test-Agenten-Nachweis (Rotphase, Ausschließlichkeit, Isolation), .vibe/project.env TESTER=test-agent.
- Remaining risks: verify.sh full-Ergebnis fehlt; Trilium-Nachweis fehlt (High); Ticket FEEDBACK/TICKETS-Nachweiseintrag und abschließendeprüfung-commit sind Teil des noch offenen Abschluss (Arbeitsablauf 10–13); kein reeller github.com-Aufruf war ausdrücklich nicht Teil der Abnahme (reporteter Grenzfall bleibt).

Damit: **CHANGES REQUIRED** — der High-Fund (behauptete, nicht existierende Trilium-Dokumentation) und das fehlende verify.sh-full-Ergebnis blockieren den Abschluss; nach Behebung (Trilium nachholen und verifizieren, B7.md-Behauptung korrigieren, finaler Prüfstand) ist eine erneute Reviewrunde erforderlich.
