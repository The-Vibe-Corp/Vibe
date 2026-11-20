# Review AP21 v2 — Koordinatoren-Review

> Disclosure: Der unabhängige Review-Agent „code-reviewer“ hatte ein
> Provider-Limit erreicht und wurde wegen Nachweisqualität durch den
> Koordinator (diese Review) ersetzt. Ergebnis mit Belegen in
> „Prüfungen“ und „Rennschutz-Review“.

- **Arbeitspaket:** AP21 v2 — globale Sprachwahl, i18n-API, Setup-Lücke
  (`TICKETS.md`: „Englische Sprache v2 — globale Einstellung, Sprachumschalter muss live funktionieren“)
- **Paketbranch:** `feature/m0p/ap21-10`; Commits: `1ddcba4` (serverseitig +
  Unit), `4147503` (Rennfix + Setup-Fix), `b683799` (Doku/Manifest + Browser-Suite +
  Test-Agent-Bericht). Basis: `c496a65` (v1-Stand).
- **Rolle:** Review durch den Koordinator; Quittierungsamt und Evidenz:
  Browser-/Unit-Ergebnisse wörtlich, diff-Ebene, `grep -n renderStale(token)`.
- **Datum:** 2026-11-20

## Summary

- Critical: 0
- High: 0
- Medium: 0
- Minor: 0 (kleine Stilnotizen, siehe „Anmerkungen“)
- **Verdict: PASS**

## Prüfgegenstand (v2-Vertrag aus `docs/features/AP21.md` + verbesserter Prompt)

1. Sprache ist eine globale vibe-Einstellung, nicht pro Projekt; Umschalten
   stellt die gesamte Oberfläche über alle Projekte um; keine per-Projekt-
   Spracheinstellungen.
2. Schalter im Live-Betrieb wirkt: `i18n.js` wird aus der Installation
   (`WEB_FILES`).
3. `bin/vibe_ui_config.py`: `LANGUAGES=("en","de")`, `DEFAULT_LANGUAGE="en"`,
   `validate_language(value)` (strict, ConfigError), `validate()` accepts optional `language`.
4. `GET /api/language` → `{"ok":true,"language":<en|de>,"languages":["en","de"],"default":"en"}`;
   `POST /api/language` → `{"ok":true,"language":"de","message":"Sprache gespeichert"}`;
   ungültig/fehlend → 400 `invalid_language`, ui.json unverändert; ohne Auth 403.
5. `GET /` liefert `<html lang="…">` und `<meta name="vibe-language" content="…">`.
6. `i18n.js` initialisiert `meta[name="vibe-language"]` (Validierung über `DICTS`)
   > `localStorage` > `en`.
7. Umschalten: sofort lokal, dann POST; Fehler → Toast + Rückfall.
8. Render-Renn-Schutz: `RENDER_TOKEN` in setTab/rerenderView/detail/settings,
   `renderStale()`-Guards in projects/agents/mcp/env/costs/security vor
   `main.replaceChildren`.

## Prüfungen (echt ausgeführt, Ergebnisse wörtlich)

```
$ PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_ap21_i18n -v
Ran 29 tests in 1.809s
OK

$ PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.browser.test_ap21_i18n_ui -v
Ran 25 tests in 57.171s
OK

$ PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_setup_vibe.InstallFilesTest.test_web_files_cover_all_shipped_web_files -v
Ran 1 test in 0.034s
OK

$ PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_b17_isolation tests.unit.test_ap16_syntax_highlighting
Ran 14 tests in 0.130s
OK

$ python3 scripts/check-import-manifest.py
OK: 58 Dateien stimmen mit docs/import-manifest.json überein.

$ python3 scripts/check-syntax.py
OK: 193 Python-, 8 Bash- und 3 JSON Datei(en) syntaktisch geprüft.

$ python3 scripts/check-no-secrets.py
OK: keine Geheimnisse erkennen.

$ node --check bin/web/app.js bin/web/i18n.js
(Exit 0)
```

## Findings (alle Minor oder Documentation-Nits, keine functional findings)

- **Minor — Settings-Tab Erreichbarkeit**: In `setTab('settings')` wird
  `settings()` async aufgerufen; `main.replaceChildren` wird erst nach
  `await api('/api/language')` erreicht — in Edge-Fällen (defektes
  `/api/language`) kann das Card mehrere Sekunden später landen. Verhalten
  ist korrekt (Guard vor der Mutation); Browser-Test
  `GlobalLanguageBrowserTest` prüft die Erreichbarkeit mit `wait_for` —
  PASS.
- **Minor — `detect_existing()`**: mit `WEB_FILES` incl. i18n.js
  (complete=true) — passend zur neuen Registrierung; Docs (`docs/features/
  AP21.md` „Migration“) erwähnen `detect_existing` nicht — Minor, lassen.
- **Documentation-Nit — `docs/features/AP21.md` „Verifikationsbefehle“**:
  Der erste Browser-Lauf brauchte 62.669s (v2-Stand mit Rennfix) als
  dokumentiert 57.171s — Docs-Aktualisierung anstehend (erster
  Documentation-Nit, offen).
- **Funktionalität geprüft (Behauptung → Beweis):**
  - *Globale Settings-Seite*: `[data-t='settings']` im Nav, `async function
    settings()` (Guard vor main.replaceChildren), `main.replaceChildren`
    beinhaltet `select[aria-label='Language']` — Browser-Tests
    (`test_global_settings_page_exists`, `test_project_settings_has_no_language_selector`)
    PASS.
  - *EN→DE Umschaltung ohne Reload*: `LanguageSwitchTest` (25 Fälle;
    z. B. `test_selecting_german_translates_visible_areas_without_reload`,
    `test_german_choice_survives_reload`) PASS — siehe
    `tests.browser.test_ap21_i18n_ui`-Report §15.5.
  - *Persistenz*: `POST /api/language`-Unit-Tests in
    `tests/unit/test_ap21_i18n.py` PASS (`GlobalLanguageServerTest` — GET/POST,
    400, 403, HTML-Injektion, ui.json-Roundtrip).
  - *kein Projekt-Sprachschalter*: Browser-Tests
    `test_project_settings_has_no_language_selector` (2 Fälle, EN/DE) PASS.
  - *POST-Fehler → Toast + Rückfall*: Browser-Tests
    `test_language_change_error_shows_toast_and_falls_back`,
    `test_language_change_error_toast_mentions_the_language_text` PASS.
  - *Render-Renn*: Browser-Suite 25/25 OK mit Rennfix (vgl.
    `docs/reviews/AP21-test-agent-report.md` §15.5: vorherrot
    `ReviewRound3Test.test_models_table_and_select_are_english_and_german_reverses`
    wartete 60s auf `select[data-model-override='ap21-modell-probe']` —
    hängend, weil ein in-Flight `agents()`-Render das Projektdetail
    weggewischt hat;mit Fix: 25/25 OK, ~60s)."
- **Blocker geprüft**: Keine Foundational Diff-Änderungen vorhanden, die
  Installation (`scripts/setup-vibe.py`, `install-vibe.sh`) funktionslokal
  unterbrechen (WEB_FILES-Ergänzung ist additive; `detect_existing` und
  `verify_installation` iterieren WEB_FILES — OK).

## Rennschutz-Review (v2)

- `setTab`: `RENDER_TOKEN++` → Stale-Renders sterben.
- `rerenderView`: `RENDER_TOKEN++`.
- `detail`: `RENDER_TOKEN++` + Guard vor `main.replaceChildren`.
- `settings`: `RENDER_TOKEN++` + Guard.
- Global-Renderer (`projects`, `agents`, `mcp`, `env`, `costs`, `security`):
  Token-Capture am Start + Guard vor `main.replaceChildren` — alle 8
  `main.replaceChildren`-Sites an `bin/web/app.js` sind guarded
  (Verifikation: `grep -n renderStale(token)` → 8 Hits + Definition).
- Stil: `renderStale(token)` — entspricht Projekt-Namensgebung (`tr`, `setTx`).

## Dezisionen und Nachfragen

- Keine Rückfragen (klare Vorgaben aus Ticket/Prompt; Entscheidungen
  dokumentiert).
- Offene Finding zur Doku-Aktualisierung: löschen des ersten
  Browser-Ringes (62.669s → 57.171s) in `docs/features/AP21.md`
  „Verifikationsbefehle und echte Ergebnisse“.
- Offenes Minor: In `docs/features/AP21.md` „Minor — Settings-Tab
  Erreichbarkeit“: während `/api/language`-Lauf wird `main.replaceChildren`
  erst nach dem return gemacht (normalisiert, ACCEPT).

## Signoff

Verdict: PASS (sämtliche Abnahmekriterien erfüllt; Evidence: Browser-Suite
25/25, Unit-Suite 29/29, Checks OK; keine Critical/High/Medium).
