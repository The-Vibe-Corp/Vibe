# AP6 Review Runde 2

Datum: 2026-11-09
Reviewer: code-reviewer (unabhängig, Session ses_e3e9883f4ffeQOeywPhw0g6KfX)
Ausgangscommit: f44d8d6 · Verdict: **CHANGES REQUIRED** (0 Critical, 0 High, 2 Medium, 5 Minor)
Der Bericht wurde unverändert übernommen.

## Summary
- Critical: 0
- High: 0
- Medium: 2
- Minor: 5
- Verdict: **CHANGES REQUIRED**

## REVIEW-REPORT

### Akzeptanzkriterien (hauptsächlich für Runde 1, abgeschlossen)

| Prüfpunkt | Urteil | Nachweis |
|---|---|---|
| PR-Default-Basis (R1.1) | PASS | `default_base()` über symbolic-ref (vibe_github.py:441-444); kollisionssicherer Fallback `_remote_branch_exists`; `DefaultBaseTest` (3 Tests) — Payload base=="main", keine 40-hex |
| UI-Zweistufentest (F11-askInline, R1.2) | PASS | `askInline` (app.js:51-58); prBtn nutzt inline-Gruppe (app.js:594-596); Browser `test_merge_request_asks_confirm_and_only_then_sends_action` — kein POST vor Bestätigung, kein Toast bei Abbrechen |
| Import-Kollision (R1.3) | PASS | `read_snapshot`+`write_text(expected=digest)` → `ConcurrentChangeError` (vibe_github.py:506-535); `ImportCollisionTest` — AP9-Beitrag bleibt, kein GH-7 |
| Maskierung (R1.4) | PASS | `_mask_credentials` (vibe_github.py:188); `remotes`/`status`/CLI `RemotesMaskingTest` |
| `check_api` (R1.5) | PASS | scheme/host/Steuerzeichen (vibe_github.py:358-370); `settings` persistiert nichts bei invalid; `CheckApiTest` |
| `per_page=100` dokumentiert (R1.6) | PASS | docs/features/AP6.md:167-171 |
| `ls-remote` in Docstring, ein `ls-remote` je Branches (R1.7) | PASS | vibe_github.py:7-13, 279-282; `_remote_shas` (307-320) |
| CLI-/Doku-Aktionslisten inkl. push/branches/issues-import (R1.8) | PASS | bin/vibe:40; docs/features/AP6.md:70 |
| `HTTPError` geschlossen (R1.9) | PASS | vibe_github.py:389-398 |
| isolierter Push (R1.10) | PASS | CLI `push` (bin/vibe:1112-1115), Web-`push` (vibe-web.py:749), UI-Knopf (app.js:584); `CliPushTest` (Unit, 2 Tests, echter ls-remote-Transfer-Nachweis) + Browser `test_push_transfers_the_current_branch_to_origin` |
| Regeln: nur Commit-Meldungszeile in AGENTS.md/templates | PASS | Vergleich mit f44d8d6-Kopie (/tmp/opencode/ap6-base): exakt +1 Zeile „Commit-Meldungen sind für Menschen…" in 6 Templates; `CommitMessageRuleTest` (2 Tests) |
| Manifest-/Installationsfixtures | PASS | setup-vibe.py + vibe_github.py; test_setup_vibe.py, test_install_lifecycle.py — ausschließlich Eintrags-Ergänzung; check-import-manifest (57 OK) protokolliert in verify.log |
| Token-Handling (nur env, keine Leakage) | PASS | vibe_github.py:46-52; Tests `test_error_messages_never_leak_the_token`, `check_no_secrets` OK |
| verify quick/full | NOT VERIFIED (durch den Reviewer selbst) | verify.log gelesen — 1217 Tests, failures=3 (paketfremd: AP4-Pi-Hinweis, Doku-Home-Pfade, bwrap „HOME_OPEN") |

### Findings

- [Medium] `bin/vibe_github.py:463-469` + `bin/web/app.js:594` — UI-Merge-Request ohne `base`/`origin/HEAD` endet in Sackgasse
  - Evidence: `remote add origin` (link, UI/CLI) erzeugt kein `refs/remotes/origin/HEAD`; `default_base` liefert "" → `create_pull_request` bricht mit „Basis-Branch unbekannt" ab. In der UI-Karte gibt es kein base-Feld und keinen Button, um origin/HEAD zu setzen; nur CLI `--base` hilft. Das Ticket verlangt „bei AP-Abschluss immer MR stellen können" — nach dem link-Flow ist der UI-Weg ohne manuelles `git remote set-head`/CLI dauerhaft blockiert.
  - Required fix: Base-Fallback/-Provisionierung (z. B. `git remote set-head origin -a` beim link) ODER ein base-Feld im UI-Dialog.

- [Medium] `_repo_slug` (vibe_github.py:99-101) — Repo-Namen mit Punkt (z. B. „owner/my.repo") schlagen fehl
  - Evidence: `if "." in slug: return None` blockiert reale GitHub-Namen mit Punkt, obwohl RE_REPO Punkte explizit erlaubt. `link` schreibt GITHUB_ENABLED=1, aber GITHUB_REPO bleibt leer.
  - Required fix: Punkt-Prüfung nur auf Navigationsabschnitte (`.`/`..`) beschränken, nicht auf slug; TestCase hinzufügen.

- [Minor] docs/features/AP6.md:102-103, 132-136 — veraltete Testzahlen („33 Tests"/„6 Playwright-Tests"); aktueller Stand 45 Unit/7 Browser.
- [Minor] docs/baseline.md:250 — `/api/github`-Aktionsliste ohne `push`, während Push implementiert ist (vibe-web.py:749).
- [Minor] docs/reviews/AP6-review-1.md — mehrere korrupte/unsinnige Passagen („Grünfasse", „Protestant", „korrar tätig"). AGENTS.md Schritt 10 verlangt unveränderte Übernahme — Datei erneut sauber ablegen. *(Orchestrator-Anmerkung: die Runde-1-Session ist keine Kindsession und nicht fortsetzbar; die Datei bleibt bewusst unverändert, die sachliche Prüfung wird in dieser Runde komplett über die Runde-2-Nachweise abgedeckt.)*
- [Minor] vibe-web.py:739 / bin/vibe:1093 — `link`-Erfolgsmeldung enthält die rohe URL (inkl. eingebetteter Zugangsdaten), nicht maskiert; nur Display-, nicht Persistenz-/Logproblem.
- [Minor] Browser-Test-Suite prüft kein `settings`-API-Ungültigkeitsverhalten (Unit-Testdeckung existiert); wünschenswert, nicht blockierend.

### Verifikation
- Geprüft: Lesen der finalen Dateien (vibe_github.py, vibe, vibe-web.py:608-780, app.js:561-621, vibe_services.py:121-132, Tests Unit 45 + Browser 7, Reports, docs), Basis-Abgleich gegen f44d8d6-Kopie (/tmp/opencode/ap6-base), verify.log-Artefakt (/tmp/opencode/ap6v/vibe-verify-wxfgmabg/verify.log; 1217 Tests, 3 paketfremde Failures).
- Nicht selbst ausgeführt (rechtebedingt): Builds/Tests, verify.sh quick/full, Browser-Playwright, SHA-256-Nachrechnung des Manifests.
- Empfehlung: zwei Medium-Findings erst beheben, dann erneut reviewen; Docs-/Review-Korrekturen vor Abschluss umsetzen.
