# Review B7 — Runde 2 (2026-11-10)

Unveränderte Abschrift der code-reviewer-Antwort auf die Nachprüfung der Runde-1-Korrekturen
(Ausgangscommit 5abce28, Umsetzung 13ac434, Doku-Nachlauf dfd3bf6).
Grobe Modellartefakte bleiben bewusst unverändert.

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Auth über die UI (Token hinterlegen/entfernen in der Karte „Git & GitHub") | PASS | bin/web/app.js:621–651 (Auth-Block, Passwortfeld, Aktionen), bin/vibe-web.py:743–752 (token.save/token.clear), bin/vibe_github.py:87–164 (Speicher/Status) | tests/browser/test_b7_github_auth_ui.py:428, 445; tests/unit/test_b7_github_auth.py:914–980 — Grün 31/7 OK reportert (Test-Agent, Nachtrag 1), von mir nicht ausgeführt |
| Fehler dauerhaft sichtbar (Karten-Fehlerbox statt nur Toast) | PASS | bin/web/app.js:612–616, 616 set in jedem Pfad, 659/664/667 | Browser-Tests file:486, 504 — reportiert |
| Fehlerklassifikation mit Anweisungstext, nie Tokeninhalt | PASS | bin/vibe_github.py (_auth_guidance, Fehlerpfade) | Unit file:773–785 (je fetch/pull/push), Browser file:504 — reportiert |
| Ruhe: token_...
   Token-Geheimhaltung (Speicher außerhalb Repos, URL-scoped Credentials, nie argv/Logs/Konfig/Antworten) | PASS | bin/vibe_github.py:64–164, 262–294 (GIT_CONFIG_* + Prozessumgebung), save_token:92–125 | Unit 249–555 (inkl. Leak-Probe file:555), Browser 445, 534, 565 — reportiert |
| Umgebung > gespeichert, REST-Scoping (gespeichert nur api.github.com) | PASS | bin/vibe_github.py:155–164, 292ff | Unit 657–742 — reportiert |
| app.js: setAuth folgt der Serverquelle (R1-Minor) | PASS | bin/web/app.js:633, 640, 644 — `setAuth(r.auth&&r.auth.set?r.auth.source:'')` an beiden Aktionen, Ausgangsstand 633 | Neuer Test file:639 `test_auth_line_follows_the_server_source_after_save_and_clear` (Umgebungstoken-Case, Fallzahl 6→7); Rotphase an beiden hartkodierten Zweigen laut Test-Agenten-Report Nachtrag 1 belegt, Grün 7/7 OK — reportiert |
| Tippfehler „Umgebungs-Konfigpur" (R1-Minor) | PASS | bin/vibe_github.py:268–272 — „Umgebungs-Konfiguration", kein „Konfigpur" im Repo (grep) | — |
| Doppeltes Satzfragment in B7.md (R1-Minor) | PASS | docs/features/B7.md:66–76 — Fragment mit Klassifikationsliste zusammengeführt, kein Redundanzrest | — |
| Trilium-Doku der AP6-Notiz RTYec92LsBSL (R1-High) | PASS | docs/features/B7.md:166–172 (referenziert Notiz + Nachtragskapitel, dfd3bf6) | Eigenständig über Trilium-MCP `get_note RTYec92LsBSL` gelesen: Kapitel „Nachtragskapitel B7 — GitHub-Zugangstoken über die Oberfläche" vorhanden (ab Zeichenoffset 8463), Commit `13ac434`, Branch, Ausgangsstand `5abce28`, Doku- und Reviewpfade, Rote/Grünphasen, Regression, verify-Zahlen und Reviewzustand Runde 1 enthalten; `utcDateModified` 2026-11-10, Hash 0Z4wRkdrBLwLTAnjY8PO |
| verify.sh quick + full | PASS (reportert) | — | B7.md:145–152 + Trilium-Kapitel: quick Exit 0; full 1298 Tests, Exit 5 mit 6 paketfremden, am Ausgangsstand 5abce28 identisch reproduzierten Fehlern; von mir nicht ausführbar (siehe Verification) |
| Test-Agent-Eigentümerschaft | PASS | tests/unit/test_b7_github_auth.py (31 `def test_`, von mir gezählt), tests/browser/test_b7_github_auth_ui.py (7 `def test_`) | .vibe/project.env: `TESTER=test-agent` vorhanden; Report docs/reviews/B7-test-agent-report.md inkl. Nachtrag 1 (Vorbedingung/Aktion/Erwartung, Rot-/Grünphasen, kein Ersatz von Assertions) |

## Findings
- No findings.

## Verification
- Change set reviewed: `5abce28..13ac434` (Implementierung, 11 Dateien, +2561/−24), `13ac434..dfd3bf6` (nur docs/features/B7.md-Trilium-Abschnitt), Arbeitsbaum sauber am Stand `dfd3bf6` auf Branch `vibe/vibe-B7-1794295794403437735-1660139-21935` (Reflog/HEAD gelesen).
- Git commands run by me: `git status --short`, `git log --oneline -8`, `git log --oneline -8` (Reflog), `git diff --stat 5abce28..13ac434`, `git diff --stat 13ac434..dfd3bf6`, `git diff 13ac434..dfd3bf6`, `git diff 5abce28..13ac434 -- bin/web/app.js`, `-- bin/vibe-web.py bin/vibe_services.py`, `-- bin/vibe`, `-- docs/import-manifest.json`, `git diff 5abce28..13ac434 --stat -- scripts/`, `--stat -- .vibe/`, `--stat -- templates/` (alle leer — Prüfwerkzeuge unverändert). Einfluss der shell-Freigabe: vier vollständige `git diff`-Ketten und nicht-Befehle; die Prüfung von scripts/.vibe/templates erfolgte in drei separaten einfachen git-Befehlen.
- Checks with supplied output (reportert von Coding-/Test-Agent bzw. Test-Agenten-Report, von mir nicht ausgeführt): Unittest 31 OK, Browser 7 OK, Regression 54/22/9 OK, AP6-gegen-AP7-Browser grün, verify.sh quick Exit 0, verify.sh full 1298 Tests/Exit 5 (6 paketfremde, an 5abce28 identische Fehler).
- Checks not independently run: alle Unittest-/Browser-Läufe, verify.sh quick/full, sha256-/MD5-Nachrechnung der Manifeste bzw. des Testdatei-Hashs (shell nur für git-Lesebefehle).
- Important areas inspected: bin/vibe_github.py (Token-Speicher/Status/REST/Git-Credential-Injektion, FUSE-Behandlung, Fehlerklassifikation), bin/vibe-web.py (token.save/clear, auth in extra), bin/vibe_services.py (Fallback auth), bin/web/app.js (setAuth-Fassung, errBox), bin/vibe (CLI getpass-Pfad), docs/features/B7.md, docs/reviews/B7-review-1.md (unverändert als R1-Abschrift), docs/reviews/B7-test-agent-report.md (Nachtrag 1), docs/import-manifest.json (B7-Eintrag, keine Geheimniswerte), .vibe/project.env (TESTER), Trilium-Notiz RTYec92LsBSL (vollständig gelesen), AGENTS.md/SPEC.md-Sicherheitsregeln (keine Geheimnisse in Antworten/Logs, FUSE-Rechte, Repository-Ordnung).
- Remaining risks: verify.sh full/quick und alle Testläufe nur als Test-Agenten-/Coding-Report verfügbar (Ausführung war mir nicht erlaubt); die Reproduzierbarkeit der 6 paketfremden Fehlschläge am Ausgangsstand 5abce28 ist nur reportiert, nicht von mir belegt; MD5/SHA-Nachweise des Testreports nicht nachgerechnet. FEEDBACK.md-B7-Eintrag ist korrekt noch offen (Abhaken erst nachert finalem PASS laut Arbeitsablauf 13).

Runde-2-Verdikt: **PASS** — alle vier Runde-1-Befunde sind nachweislich behoben; keine offenen Critical/High/Medium-Findungen.
