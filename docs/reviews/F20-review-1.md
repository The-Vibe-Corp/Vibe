# F20 Review — Runde 1 (unabhängiger code-reviewer)

Datum: 2026-11-08
Stand: d9690e7 → Arbeitskopie (Branch vibe/vibe-F20-1794094233248968013-2071287-14400)
Geprüft von: Agent `code-reviewer` (read-only, unabhängige Sitzung)

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Pi-Auswahl über `<Zustand>/harness.json` via `read_selection` (Ausnahme bei unlesbarer Auswahl → opencode-Verhalten) | PASS | `bin/vibe-web.py:321-324` (steer), `bin/vibe-web.py:581-589` (/api/server, bestehend), `bin/vibe_harness.py:100-126` | Unit `test_f20_harness_dashboard_api.py`: `test_unknown_harness_value_keeps_the_previous_behavior` (Auslieferung statt Ablehnung); vom Coding-Agent gemeldet: „Ran 8 tests OK“ |
| `/api/steer` lehnt bei Pi VOR dem Session-Bezug mit verständlicher Meldung ab (keine sessionbezogene Meldung) | PASS | `bin/vibe-web.py:325-330` — Ablehnung vor `run_is_active`/`subagents_of`/Kennwortbezug; Meldung nennt Pi, Print-Modus, `--no-session`, fortsetzbare Session | Unit `test_steer_with_selected_pi_is_rejected_without_delivery_attempt` (Status 400, `error.code` „rejected“, Meldung enthält Pi-Grund, nicht `SESSION_MISSING_MESSAGE`); Reihenfolge im Code bestätigt |
| Kein Zustellversuch an den opencode-Server, keine Protokollkennzeile | PASS | `bin/vibe-web.py:325-330` (early return) | Unit-Test beweist fehlenden Zustellversuch über Vorforderung mit Request-Protokollierung (`posts()`-Zähler unverändert, `auth_ok`-Attrappe) und fehlende Kennzeile im Log; Auslieferungsmuster in Regressionstests mit Basic-Auth-Attrappe |
| Keine opencode-Server-Steuerung in der Kopfleiste bei Pi, „Dashboard beenden“ bleibt | PASS | `bin/web/app.js:66-73` (isPi-Spread: kein Server-Status/Button, Pi-Hinweis) | Browser `test_f20_harness_ui.py`: `test_server_box_runs_pi_without_opencode_server_controls`; Regression `test_server_box_keeps_opencode_controls` |
| Kein opencode-Weblink im Projekt-Detail bei Pi | PASS | `bin/web/app.js:116,132` | Browser: `test_project_detail_has_no_opencode_weblink`; Regression Link count 1 |
| Steuerkarte nennt bei Pi Print-Modus-`--no-session` statt opencode-Session | PASS | `bin/web/app.js:352,369-371` | Browser: `test_steer_card_names_pi_print_limit` |
| Subagenten-Karte erwähnt bei Pi die Grenze | PASS | `bin/web/app.js:377,382-383` | Browser: `test_subagent_card_notes_pi_limit`; Regression bestätigt |
| Agenten-/(Modell-)Ansicht auf Pi umgestellt (Prompt-Quelle, Pi-Login, `pi --list-models`) | PASS | `bin/web/app.js:650,684-685,688,698,719-720` | Browser: `test_models_detail_points_to_pi_list_models`, `test_profiles_hint_names_pi_instead_of_opencode_login`, `test_agents_dir_hint_explains_prompt_source` |
| Sandbox-Karte beschreibt bei Pi die Pi-Laufart statt opencode-Server | PASS | `bin/web/app.js:442,450-452` | Browser: `test_sandbox_card_describes_pi_runtime` |
| MCP-Tab weist bei Pi auf Nicht-Einbindung hin statt „opencode mcp auth“ | PASS | `bin/web/app.js:864,875` | Browser: `test_mcp_hint_points_to_pi_limit` |
| /api/server meldet bei Pi `harness:"pi"`, `server_supported:false` | PASS | `bin/vibe-web.py:581-589` | Unit: `test_server_reports_pi_without_server_support`, `test_server_reports_opencode_support_by_default`, `test_server_reports_explicit_opencode_selection_as_supported` |
| Regression ohne/unbekannter Auswahl unverändert (opencode) | PASS | Frontend-Fallback `'opencode'` in `app.js:76`; Backend `vibe-web.py:323-324` | Unit: `test_steer_regression_default_selection_is_delivered_as_before`, `test_steer_regression_explicit_opencode_selection_is_delivered`, `test_unknown_harness_value_keeps_the_previous_behavior`; Browser `OpencodeRegressionUiTest` (3 Tests) |
| Kein Geheimnis-Leak im neuen Code | PASS | `bin/vibe-web.py` — `redact(msg)` bleibt aktiv; steer-Ablehnung enthält kein Geheimnis | Unit: `test_password_secret_never_leaves_api_results` |
| Manifest/Doku aktualisiert | PASS | `docs/import-manifest.json` (Prüfsummen/Größen, Changelog F20), `docs/compatibility.md:58-66` | `scripts/verify.sh quick` vom Coding-Agent gemeldet OK — nicht unabhängig laut geprüft |

## Findings
- [Minor] `docs/import-manifest.json` — Changelog-Eintrag F20 bricht Einrückungsformat
  (alle bisherigen Einträge nutzen 2/3-Leerzeichen-Einrückung; der F20-Eintrag begann
  ohne Einrückung — JSON bleibt gültig, aber das von F25 etablierte Format wird
  verletzt). Required fix: Eintrag F20 in derselben Einrückung schreiben.
- [Minor] `docs/features/F20.md` — Zählwerte des verify-full-Laufs stimmen nicht mit
  den tatsächlich gemeldeten Läufen überein (Doku nannte failures=35/37/40, tatsächlich
  failures=36, errors=2; Baseline failures=36, errors=3). Required fix: Ziffern auf
  die belegten Läufe korrigieren.
- [Minor] `bin/web/app.js` — Beenden-Tooltip nennt bei Pi noch „nicht opencode“.
  Required fix: Tooltip bei Pi neutral formulieren.

## Verification
- Change set reviewed: `d9690e7..working tree` (modified: `bin/vibe-web.py`,
  `bin/web/app.js`, `docs/compatibility.md`, `docs/import-manifest.json`; untracked
  neu: `tests/unit/test_f20_harness_dashboard_api.py` (585 Zeilen, 8 Tests),
  `tests/browser/test_f20_harness_ui.py` (514 Zeilen, 12 Playwright-Tests),
  `docs/features/F20.md`). Alle Dateien vollständig gelesen.
- Von mir ausgeführte Git-Befehle: `git status --short`, `git log --oneline`,
  `git diff d9690e7 --stat`, `git diff d9690e7 -- bin/vibe-web.py`,
  `git diff d9690e7 -- bin/web/app.js`, `git diff d9690e7 -- docs/import-manifest.json
  docs/compatibility.md`; Grep/Lesezugriffe auf `bin/vibe_harness.py`,
  `bin/vibe-web.py`, `bin/web/app.js`, FEEDBACK.md.
- Mit Agent-Nachweis (vom Coding-Agent ausgeführt, nicht von mir): Unit-Lauf
  „Ran 8 tests OK“, Playwright „Ran 12 tests OK“, `verify.sh quick` OK,
  `tests.unit.test_release` 14 OK, `verify.sh full` 1072 Tests FAILED
  (failures=36, errors=2) mit Baseline-Klon d9690e7 (FAILED failures=36, errors=3;
  identische bekannte tmux/bwrap-Umgebungsgrenzen, keine F20-Fälle).
- Checks not independently run: alle Build-/Test-/Prüf-Skripte (nicht erlaubt), die
  SHA-256-Prüfsummen im Manifest, die Trilium-Dokumentation.
- Important areas inspected: `steer_project()` inkl. Reihenfolge Session-Bezug,
  `/api/server`-Endpoint, `read_selection()`-Fallbacks (unlesbar/unbekannt →
  opencode), alle `isPi`-Stellen in app.js mit ausstehenden opencode-Stellen
  (Restnennungen sind bewusst opencode-fachlich: Agentendateiformat
  `~/.config/opencode/agents`, `/tmp/opencode`-Pfad, Katalog-ID-Präfix `opencode/`,
  Harness-Auswahlkarte), beide Testdateien vollständig (keine leeren Tests, keine
  Skips/Catch-all, keine geschwächten Assertions), F20.md vs. Code, compatibility.md.
- Remaining risks: 1) Provenienz der Testdateien aus einer früheren Test-Agent-Sitzung
  desselben Arbeitspakets (Nutzungslimit-Abbruch, FEEDBACK.md Z. 262) ist aus der
  Änderungshistorie nicht unabhängig belegbar; im akzeptierten Muster wie F19/B1
  dokumentiert; Akzeptanz der Tests hier rein fachlich geprüft. 2) verify-full-
  Baseline-Fehler sind der Umgebung zuzuschreiben; Ziffern siehe Minor 2. 3)
  Manifest-Prüfsummen nicht unabhängig nachgeprüft.

Verdict: PASS
