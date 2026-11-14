# Test-Agent-Report — AP6 „Vorbereitung für github Repo"

Autor: unabhängiger Test-Agent (`TESTER=test-agent`)
Datum: 2026-11-09
Grundlage: Arbeitspaket AP6 (TICKETS.md, Zielcommit f44d8d6), SPEC.md, AGENTS.md.
Kein Implementierungsdiff vorhanden; die Tests wurden aus dem Arbeitspaket
hergeleitet, nicht aus der Implementierung.

## Umsetzungskontrakt (fachliche Schnittstelle)

Die Implementierung erfüllt den folgenden Kontrakt (Schnittstellenverabredung
mit dem Coding-Agenten):

- Neues Modul `bin/vibe_github.py` (nur Python-Standardbibliothek):
  - `read_config(env_path)` -> `{"enabled": bool, "repo": "owner/name", "label": str, "api": str}`
  - `status(project_path)` -> Offline-Ansicht mit `remotes`, `branch`,
    `ahead`, `behind`, `unpushed` (kein Netz)
  - `branches(project_path)` -> Liste `{name, current, ahead, behind}`
  - `fetch(project_path)` / `pull(project_path)` -> `(ok, message)`
  - `push(project_path, branch)` -> `(ok, message)`, nur Argumentlisten
  - `list_issues(repo, label, api=None, token=None)` -> Liste mit
    `number` / `title` / `html_url`
  - `import_issues_into_tickets(project_path, issues)` -> fügt fehlende
    Einträge `- [ ] GH-<num> <titel>` in TICKETS.md ein, atomar und idempotent
  - `create_pull_request(...)` -> dict mit `url`; Token nur aus
    `GITHUB_TOKEN|GH_TOKEN`; ohne Token klare Fehlermeldung und keine Anfrage;
    API-Basis konfigurierbar (Standard `https://api.github.com`)
  - Keine Automatik: keine Modulfunktion pusht oder mergt von selbst.
- CLI in `bin/vibe`: `vibe github <projekt> status|link <url>|unlink|fetch|pull|issues|issues-import|pr [--confirm]`;
  `pr` ohne `--confirm` darf weder pushen noch die API aufrufen; `link` setzt
  das Git-Remote `origin` und schreibt GITHUB_ENABLED/GITHUB_REPO.
- Regelansatz: `GENERAL_RULES` und alle `templates/*/AGENTS.md` fordern im
  Block „Ordnung im Git halten" Commit-Meldungen „für Menschen" und auf das
  „Wesentliche" reduziert.
- Web-API: `GET /api/github?name=...` (Offline-Ansicht) und
  `POST /api/github` mit Aktionen link/settings/fetch/pull/issues/pr,
  Auth-Pflicht wie andere Schreibendpunkte.
- Config nur in `.vibe/project.env` (Keys GITHUB_ENABLED, GITHUB_REPO,
  GITHUB_LABEL, GITHUB_API), Schreibzugriff über das bestehende
  `set_env_values` der CLI.

## Testdateien und Befehle

| Datei | Umfang |
|---|---|
| `tests/unit/test_ap06_github.py` | 33 Unit-Tests in 9 Klassen |
| `tests/browser/test_ap06_github_ui.py` | 6 Browser-Tests in 1 Klasse |

Befehle (aus dem Worktree-Arbeitsverzeichnis):

```
python3 -m unittest tests.unit.test_ap06_github -v
python3 -m unittest tests.browser.test_ap06_github_ui -v
```

Beide Dateien sind eigenständig lauffähig (unittest discover, keine Adapter).
Isolation: `tempfile.TemporaryDirectory`, eigener Port für Fake-API und
Dashboard, Fake-GitHub-Server nur an 127.0.0.1, keine echten Aufrufe nach
github.com, kein produktiver `$VIBE`/`_toolchain`-Pfad, keine Secrets: die Tests entfernen
GITHUB_TOKEN/GH_TOKEN aus der Umgebung und setzen keine davon, Git mit fester
Testidentität in Tempverzeichnissen.

## Testfälle

### Unit-Tests (tests/unit/test_ap06_github.py)

Konfiguration — Akzeptanzkriterium: GitHub optional und pro Projekt:

- `ReadConfigDefaultsTest.test_missing_keys_mean_disabled_with_vibe_label_and_official_api`
  Vorbedingung: project.env ohne GitHub-Keys. Aktion: read_config. Erwartung:
  enabled=False, repo="", label="vibe", api="https://api.github.com".
- `ReadConfigDefaultsTest.test_missing_project_env_file_reports_disabled_github`
  Erwartung: fehlende Datei -> enabled=False, kein Absturz.
- `ReadConfigDefaultsTest.test_enabled_flag_values_are_parsed`
  Erwartung: GITHUB_ENABLED=1/0/true -> True/False/True.
- `ReadConfigDefaultsTest.test_quoted_values_keep_their_content`
  Erwartung: KEY="value"-Format wird inhaltlich übernommen (Repo „owner/name",
  Label, API).
- `ConfigWriteTest.test_setting_github_keys_preserves_existing_lines`
  Erwartung: set_env_values(GITHUB_…) lässt TYPE/TESTER/SANDBOX unangetastet
  (Fachliches Kriterium: pro-Projekt-Schalter über das gemeinsame env-Update).
- `ConfigWriteTest.test_setting_github_keys_in_a_crlf_file_keeps_crlf_style`
  Erwartung: Zeilenenden bleiben erhalten.
- `ConfigWriteTest.test_saved_github_config_round_trips_through_read_config`
  Erwartung: alle vier Keys schreiben -> read_config liefert identische Werte.

Link/Unlink — Akzeptanzkriterium: Verknüpfung mit GitHub-Repository:

- `LinkUnlinkTest.test_link_sets_origin_url_and_persists_github_keys`
  Erwartung: Remote `origin` auf die URL gesetzt, GITHUB_ENABLED="1" und
  GITHUB_REPO="owner/name" in project.env, andere Zeilen bleiben.
- `LinkUnlinkTest.test_link_with_local_file_remote_also_lands_in_the_config`
  Erwartung: analog für file://-Remote (nur im Testbetrieb).
- `LinkUnlinkTest.test_unlink_removes_origin_but_keeps_other_lines_and_remotes`
  Erwartung: origin entfernt, daneben liegender Remote `upstream` bleibt,
  env-Zeilen bleiben.
- `LinkUnlinkTest.test_invalid_url_is_refused_without_any_change`
  Erwartung: ungültige URL (ohne owner/name) -> Remote und env unverändert.

Fetch/Pull/Push und Aufrufart — Akzeptanzkriterium: Updates und Branches
bewusst unterstützen, ausschließlich Feature-Branch, keine Shell-Injektion:

- `RemoteOpsTest.test_push_publishes_the_local_commit_to_origin`
- `RemoteOpsTest.test_pull_absorbs_remote_updates`
- `RemoteOpsTest.test_diverged_pull_fails_and_keeps_the_local_state_intact`
  (differierende Branches -> pull scheitert mit Meldung, HEAD und Arbeitskopie
  bleiben unverändert)
- `RemoteOpsTest.test_git_calls_use_plain_argument_lists_without_shell`
  (Spy über subprocess.run -> Argumentlisten aus Strings, kein shell=True)
- `RemoteOpsTest.test_fetch_reports_an_unreachable_remote_without_crashing`

Status/Branches — Akzeptanzkriterium: Branches und Updates in der UI sichtbar:

- `StatusAndBranchesTest.test_status_reports_the_essential_github_and_remote_facts`
- `StatusAndBranchesTest.test_unpushed_tracks_the_published_history`
- `StatusAndBranchesTest.test_branches_list_local_names_mark_current_and_report_ahead_behind`
  (aktueller Branch markiert; divergierte `feature` vs. `origin/feature` ->
  ahead=1, behind=1)

GitHub-API-Schicht — Akzeptanzkriterium: Merge-Request, Issues als
Arbeitspakete, optionale Integration:

- `GitHubHttpLayerTest.test_list_issues_filters_by_label_and_returns_number_title_url`
- `GitHubHttpLayerTest.test_create_pull_request_posts_bearer_token_and_returns_the_url`
- `GitHubHttpLayerTest.test_create_pull_request_sends_exactly_one_api_request`
- `GitHubHttpLayerTest.test_missing_token_blocks_the_pull_request_without_any_request`
  (Fehler beginnt mit „Kein GitHub-Zugangstoken", keine Anfrage)
- `GitHubHttpLayerTest.test_pull_request_resolves_the_token_from_the_environment`
- `GitHubHttpLayerTest.test_error_status_is_mapped_to_a_clear_message` (422)
- `GitHubHttpLayerTest.test_error_messages_never_leak_the_token` (401)

TICKETS-Import — Akzeptanzkriterium: GitHub-Issues als Arbeitspakete:

- `IssuesImportTest.test_import_appends_vibe_issues_in_ticket_format_and_is_idempotent`
  (Format `- [ ] GH-7 ...`, Bug-Issue 8 bleibt draußen, zweiter Import
  ändert nichts)
- `IssuesImportTest.test_import_keeps_existing_ticket_entries_unchanged`
- `IssuesImportTest.test_imported_items_are_parseable_as_open_tickets`
  (existierender Ticket-Parser liest GH-7 als offen)

CLI — Akzeptanzkriterien: Merge-Request bewusst, kein impliziter Netzzugriff:

- `CliGithubTest.test_status_prints_branch_and_remote_facts`
- `CliGithubTest.test_pr_without_confirm_never_pushes_or_calls_the_api`
  (pr ohne --confirm -> Fake-API bleibt ohne Anfrage, HEAD unverändert)

Regeln — Akzeptanzkriterium: menschlich verständliche, wesentliche Commits:

- `CommitMessageRuleTest.test_general_rules_demand_human_readable_essential_commit_messages`
  (im Block „Ordnung im Git halten" der GENERAL_RULES-Konstante stehen
  „Commit-Meldungen", „für Menschen" und „Wesentliche")
- `CommitMessageRuleTest.test_all_shipped_templates_contain_the_same_commit_rule`
  (alle `templates/*/AGENTS.md` tragen denselben GENERAL_RULES-Block inkl.
  Commit-Meldungs-Regel, Muster `TemplateRulesTest` in
  `tests/unit/test_project_management.py`)

### Browser-Tests (tests/browser/test_ap06_github_ui.py)

Vorbedingung: echtes Dashboard gegen temporäre Pseudo-Installation (Muster test_ap04_harness_ui),
Projekt `gh-demo` mit GITHUB_ENABLED="1", GITHUB_REPO="owner/name",
GITHUB_API auf lokalen Fake-Server, echtem lokalen Git-Origin (file://);
Projekt `gh-off` ohne GitHub-Konfiguration; Dashboard-Prozess ohne Token.

- `test_git_card_shows_settings_fields_and_saved_state` — Karte „Git & GitHub"
  sichtbar, Aktiv-Toggle angehakt, Felder für Repo („owner/name") und Label
  („vibe") vorhanden.
- `test_settings_changed_in_the_card_are_persisted_without_manual_reload` —
  Ändern des Repo-Feldes auf owner/renamed und Speichern ->
  `GITHUB_REPO="owner/renamed"` in project.env ohne manuelles Nachladen;
  andere Zeilen bleiben; die Karte bleibt ohne page.reload() sichtbar.
- `test_import_adds_vibe_issues_to_tickets_and_keeps_bugs_out` — Import-Button
  -> TICKETS.md enthält `- [ ] GH-7 ...` mit Titel, aber NIEMALS `GH-8`
  (stärkster Label-Filter-Nachweis).
- `test_merge_request_button_lives_in_the_card_and_errors_clearly_without_token`
  — Merge-Request-Button nur im aktivierten Projekt; Klick ohne Token ->
  klare Fehlermeldung („Kein GitHub…"/„Fehler"), Fake-API bleibt ohne
  POST /pulls, Dashboard läuft stabil weiter.
- `test_disabled_project_shows_the_card_without_merge_request` — `gh-off`:
  Karte vorhanden (deaktivierter Zustand), Toggle unbelegt, kein
  Merge-Request-Button.
- `test_branch_overview_and_fetch_pull_actions_are_visible` — Branch-Name
  „main" sichtbar, Buttons für Fetch/Abrufen und Pull vorhanden; Klick auf
  Abrufen zeigt eine Meldung und erzeugt keine Fake-API-Anfrage.

## Rotphase (tatsächlich ausgeführt)

### 1) Unit-Tests

- Befehl: `python3 -m unittest tests.unit.test_ap06_github -v` (Worktree-Root)
- Protokoll: `/tmp/opencode/ap6-unit-red.log`
- Ergebnis: `Ran 33 tests in 3.717s — FAILED (errors=33)`, Exit-Code 1
- Fehlerbild: alle 33 Fälle scheitern korrekt, weil das Modul fehlt.
  Das Laden von `bin/vibe_github.py` (als Modul) erzeugt:
  `FileNotFoundError: [Errno 2] No such file or directory: .../bin/vibe_github.py`.
  Sobald das Modul existiert, laufen die Ladefehler in echte fachliche
  Assertions aus bzw. CLI-Tests schlagen dann sichtbar mit
  `AttributeError/TypeError` auf fehlendes `cmd_github` (Log in der Quelle).

### 2) Browser-Tests (zweistufig dokumentiert)

- **Erster Versuch (Wortlauf des vorgesehenen Befehls**,
  Protokoll `/tmp/opencode/ap6-browser-red.log`): Exit-Code 1, `Ran 0 tests`.
  Ursache: Playwright findet im durch OpenCode umgeleiteten
  `XDG_CACHE_HOME` (`/tmp/opencode/vibe-sandbox/.../cache/ms-playwright`)
  keinen Chromium. Das betrifft die Umgebung, nicht die Tests —
  derselbe Befehl schlägt auch für das bestehende
  `tests.browser.test_ap04_harness_ui` identisch fehl (nachgestellt und
  protokolliert).
- **Ausführungskorrektur nach etabliertem Muster** `scripts/verify.py`
  (dort Zeilen ~225–262): `PLAYWRIGHT_BROWSERS_PATH` wird auf einen
  vorhandenen Browsercache (`~/.cache/ms-playwright`) gesetzt; nur lesend,
  kein Download, kein produktiver Pfad als Arbeitsverzeichnis. Die
  Browser-Test-Datei übernimmt denselben Guard am Dateianfang
  (`os.environ.setdefault`, nur wenn das Verzeichnis existiert), genau das
  würde auf dem normalen Host ohnehin gelten, so dass der Testbefehl ihn nicht
  explizit mitliefern muss.
- **Zweiter Versuch (echter Lauf, Protokoll `/tmp/opencode/ap6-browser-red2.log`)**
  Befehl: `python3 -m unittest tests.browser.test_ap06_github_ui -v`
  (mit Inline-Guard) → Exit-Code 1.
  - Ergebnis: `Ran 6 tests in 92.250s — FAILED (errors=6)`
  - Fehlerbild: alle 6 Fälle laufen in die echte Oberfläche hinein
    (Projektliste, Detailansicht, Einstellungen-Tab) und scheitern
    konsistent am fehlenden Dashboard-Feature:
    `TimeoutError: Locator.wait_for: Timeout 15000ms exceeded — waiting for
    locator(".card").filter(has_text="Git & GitHub").first to be visible`.
    Genau das erwartbar fehlende Feature (Karte „Git & GitHub"), nicht ein
    gebrochenes Testgerüst.

## Dokumentierte Anpassungspunkte für die Implementierung

- `cli.cmd_github` wird mit Keyword-Argumenten (`action=`, `url=`, `title=`,
  `out=`) aufgerufen. Wählt die Implementierung andere Parameternamen, wird
  das als klarer `TypeError` sichtbar — die Tests dürfen dann auf die
  vereinbarte Signatur umgestellt werden, nicht abgeschwächt werden.
- Die Browser-Tests erkennen die Repo-/Label-Felder über den vorgeladenen
  Wert (`owner/name` / `vibe`) statt über ein festes Markup — verbindlich ist
  das Verhalten (Feld existiert und wirkt), nicht ein konkreter Selektor.
- Der Labelfilter der Issue-Ansicht wird großzügig erkannt: verbindlich
  bewiesen ist die Wirksamkeit (Bug-Issue 8 landet nie in TICKETS.md),
  nicht der konkrete Selektor des Eingabefelds.

## Nächste Schritte (für Coding-Agent und Reviewer)

1. Implementierung gegen den oben stehenden Kontrakt umsetzen; danach
   beide Testbefehle erneut ausführen und die Protokolle beilegen. Der
   Test-Agent prüft dann erneut und vergleicht mit dem dokumentierten
   Rotphasen-Stand.
2. Hinweise für den Reviewer: Die Browser-Tests schreiben ausschließlich
   in die temporäre Testumgebung, nie in eine produktive Installation.
   Der Guard für `PLAYWRIGHT_BROWSERS_PATH` ist bewusst nur lesend und
   berührt keine produktive Konfiguration. Die Phrasen der
   Commit-Meldungs-Regel („Commit-Meldungen", „für Menschen",
   „Wesentliche") sind als Minimalanker gesetzt; wählt die
   Implementierung andere Formulierungen, ist das mit dem Test-Agenten
   zu klären, bevor die Assertions angepasst oder gelockert werden
   (Abmilderung ist keine Option).

## Verbleibende Lücken

- Grüner Beweis steht aus: Implementierung (`bin/vibe_github.py`,
  CLI-Kommando, Web-API `/api/github`, UI-Karte, Regel-Erweiterung in
  GENERAL_RULES und templates) existiert noch nicht. Nur nach der
  Implementierung gilt der Grünzustand als bestätigt.
- Barrierefreiheit der neuen Karte (ARIA/Tastatur) ist nicht Teil der
  Testagent-Suiten; dies bleibt an die UI-Prüfung des Coding-/Review-Agenten.
- Der Abgleich mit der echten GitHub-API ist ausdrücklich nicht geprüft
  (Regeln: keine echten externen Dienste und keine Modellkosten ohne
  Freigabe). Die Tests beweisen den Kontrakt vollständig gegen den
  lokalen Fake-API-Server.

## Fixlauf (Grünfassung der Unit-Suite)

Datum: 2026-11-09. Der Coding-Agent implementierte AP6 (bin/vibe_github.py,
CLI, Web-API, UI, Regelblöcke) und korrigierte `_push_state` (fehlende
Fern-Objekte werden gezielt nachgezogen) sowie `_revision_compare_local`
(zwei leere Werte bleiben 0/0). Danach wurden meine vier verbliebenen
Testdefekte analysiert — sie lagen sämtlich in meinen Testfällen, nicht im
Produktcode:

1. `ConfigWriteTest.test_setting_github_keys_in_a_crlf_file_keeps_crlf_style`:
   Python normalisiert im Textkanal (`read_text`) die Zeilenenden, wodurch
   der CRLF-Zustand prinzipbedingt nicht nachweisbar war (AssertionError:
   `TYPE=generic\r\nTESTER=test-agent\r\n` nicht enthalten). Fix im Test:
   Lesen über `read_bytes().decode("utf-8")`; die Assertion gegenüber den
   gelesenen Bytes bleibt unverändert. Der Produktcode schreibt korrekt
   (CRLF bleibt per os.replace bytegenau erhalten).
2. `RemoteOpsTest`-Fixture (3 ERRORs): das Bare-Origin wurde mit
   `git init --bare` ohne `-b main` angelegt; in der isolierten Testumgebung
   (`GIT_CONFIG_GLOBAL=/dev/null`, kein init.defaultBranch) hieß der
   Bare-Default-Branch `master`. `git clone` meldete „remote HEAD refers to
   nonexistent reference", danach fehlte im Klon die erwartete Arbeit
   (`FileNotFoundError` bei `arbeit.txt`/`partner.txt`), bevor der
   Produktcode überhaupt ausgeführt wurde. Fix im Test: `make_bare()` legt
   das Bare-Origin jetzt mit `git init -q --bare -b main` an.
3. Zusätzlich dabei offengelegt:
   `test_pull_absorbs_remote_updates` vergaß den Push des Kollaborators an
   das Origin (`git(contributor, "push", ...)`, sichtbar in
   green2/run2); ohne Push konnte der Pull die Änderung nicht empfangen.
   Fix im Test: Push-Zeile ergänzt.

Geänderte Teststellen (nur tests/unit/test_ap06_github.py; Produktcode und
Rest der Testfälle unverändert):
- `make_bare()` (Zeilen ~276–281): Bare-Repo-Init mit `-b main` erweitert und kommentiert.
- `test_setting_github_keys_in_a_crlf_file_keeps_crlf_style` (Zeilen ~360–371): `read_bytes`.
- `test_pull_absorbs_remote_updates` (Zeilen ~465–476): Push-Zeile ergänzt.

Laufprotokolle:

- 1. Lauf nach Implementierung: `Ran 33 tests … FAILED (failures=1, errors=3)`,
  Exit-Code 1 — `/tmp/opencode/ap6-unit-green1.log`
- 2. Lauf (CRLF+make_bare behoben): `Ran 33 tests in 5.340s — errors=1`,
  verbleibender ERROR `test_pull_absorbs_remote_updates` —
  `/tmp/opencode/ap6-unit-green2.log`
- 3. Lauf (Push-Ergänzung): `Ran 33 tests in 5.392s — OK`, Exit-Code 0 —
  `/tmp/opencode/ap6-unit-green3.log`

Die dokumentierte Rotphase (alle 33 Fälle rot mit `FileNotFoundError` bei
`bin/vibe_github.py`) bleibt unverändert gültig; keine anderen Stellen sind
verändert, keine Produktartefakte und kein Commit/Git-Operation von mir.

- 4. Lauf (Secret-Prüfung): `scripts/check-no-secrets.py` meldete
  `FEHLT: tests/unit/test_ap06_github.py:684: Zugangsdaten-Zuweisung` —
  das Fake-Literal (16 Zeichen lang) traf die Heuristik (Zugangsdaten-
  Zuweisung mit Literal ≥ 16 Zeichen). Fix im Test: Literal auf
  `secret = "t-absolut"` (9 Zeichen, Kommentar klärt den Fake-Charakter)
  gekürzt; `self.assertNotIn(secret, message)`
  bleibt unverändert und prüft weiterhin gegen die Variable. Danach:
  `python3 -m unittest tests.unit.test_ap06_github -v` →
  `Ran 33 tests in 6.468s — OK`, Exit-Code 0
  (`/tmp/opencode/ap6-unit-secret-fix.log`);
  `python3 scripts/check-no-secrets.py` →
  `OK: keine Geheimnisse erkannt.`, Exit-Code 0. Der Fixture-Token
  `token="t-supersecret"` (13 Zeichen) blieb unverändert.

- 5. Lauf (Installationskit): Der Coding-Agent nahm `vibe_github.py` in
  `PROGRAM_FILES` von `scripts/setup-vibe.py` auf (V-021-Muster: neue
  Programmdaten werden mitkopiert). Das Kit-Fixture in
  `tests/unit/test_setup_vibe.py` kannte das Modul noch nicht
  („Unvollständiges Quellverzeichnis: …/bin/vibe_github.py fehlt",
  6 ERRORs). Fix im Test-Fixture: `"vibe_github.py"` in der
  `PROGRAM_FILES`-Liste ergänzt. Danach:
  `python3 -m unittest tests.unit.test_setup_vibe -v` →
  `Ran 49 tests in 0.315s — OK`, Exit-Code 0
  (`/tmp/opencode/ap6-setup-fix.log`);
  `python3 -m unittest tests.unit.test_ap06_github` →
  `Ran 33 tests in 6.442s — OK`, Exit-Code 0
  (`/tmp/opencode/ap6-unit-after-setup.log`). Es traten keine weiteren
  Failures auf (auch nicht im Dry-Run-Darstellungsbereich).

- 6. Lauf (Lebenzyklus-Installationskit): `tests/unit/test_install_lifecycle.py`
  hält dieselbe `PROGRAM_FILES`-Abbildung mit Gleichheits-Assertion
  („Testabbild und Setup müssen dieselben Programmmodule kennen") und ein
  Kit-Fixture, das das neu installierte Modul noch nicht enthielt
  (ERRORs u. a. in `test_fresh_install_copies_all_program_modules_and_writes_version`
  und `test_verify_installation_reports_a_missing_web_asset`). Fix im Test:
  `vibe_github.py` in die Testabbild (Kit-Fixture iteriert dieselbe Liste)
  aufgenommen; die Gleichheits-Asserts blieben exakt erhalten. Danach:
  `python3 -m unittest tests.unit.test_install_lifecycle -v` →
  `Ran 43 tests in 0.158s — OK`, Exit-Code 0
  (`/tmp/opencode/ap6-lifecycle-fix.log`);
  Kombilauf `tests.unit.test_setup_vibe + tests.unit.test_ap06_github +
  tests.browser.test_ap06_github_ui` → `Ran 88 tests in 9.222s — OK`,
  Exit-Code 0 (`/tmp/opencode/ap6-combo.log`) — damit sind auch die
  Browser-Tests für AP6 erstmals grün.

## Review-Befund-Testfälle (Runde 1)

Der code-reviewer (docs/reviews/AP6-review-1.md) verlangte weitere
getestete Verhaltensweisen. Testfälle wurden vorher (Rotphase) geschrieben; die
Implementierung durch den Coding-Agenten folgt. Testbefehle unverändert
siehe oben; zusätzliche Rotphasenprotokolle:
`/tmp/opencode/ap6-review1-unit-red.log` (43 Tests, davon 10 neu) und
`/tmp/opencode/ap6-review1-browser-red.log`.

### Neue Unit-Tests (tests/unit/test_ap06_github.py)

1. Klasse `DefaultBaseTest` (Medium: PR-Default-Basis):
   - `default_base_resolves_the_branch_name_of_origin_head`
     Vorbedingung: Projekt mit origin (file://, Bare-Repo mit `-b main`),
     symbolic origin/HEAD → origin/main. Aktion: `default_base(project)`.
     Erwartet: „main" als Branchname, keine SHA.
   - `pr_without_base_names_the_default_branch_not_a_commit_sha`
     Aktion: `create_pull_request(..., base=None)` gegen Fake-API. Erwartet:
     gesendete Payload `base == "main"`, nicht 40-hex-SHA.
   - `unknown_default_base_fails_usably_without_any_request`
     Aktion: origin/HEAD auf nicht existierenden Branch zeigen lassen,
     erneut PR ohne base. Erwartet: verständliche Ausnahme, keine Anfrage
     an die Fake-API.
2. Klasse `ImportCollisionTest` (Medium: Kollisionsprüfung import):
   Vorbedingung: TICKETS.md; der Test legt einen Zeitpunkthinweis auf die
   atomare Schreibnaht `vibe_storage.read_snapshot` (bewusste Naht:
   liest das Modul die Integrität über eine andere Methode, ist die
   Naht dorthin umzuziehen — die fachlichen Assertions bleiben
   unverändert). Zwischen Lese- und Schreibzeit ändert ein externer
   Schreiber TICKETS.md (Block „AP9 Eingriff").
   - `concurrent_ticket_change_is_reported_and_file_stays_intact`:
     Erwartet: ValueError mit „zwischenzeitlich" und „Import" in der
     Meldung; Datei enthält den Fremdbeitrag und NIE „GH-7".
   - `import_without_interference_keeps_working`: ohne Eingriff läuft der
     Import normal durch („- [ ] GH-7" vorhanden).
3. Klasse `RemotesMaskingTest` (Low→Umsetzung: URL-Maskierung):
   Vorbedingung: origin mit eingebetteten kurzen Fake-Kontodaten,
   upstream ohne Kontodaten.
   - `remotes_masks_embedded_credentials_and_keeps_the_rest`: Erwartet:
     `***` an den Kontodaten, Schema/Host/Pfad stehen, Kontodaten erscheinen
     in der Rückgabe nicht.
   - `status_never_exposes_the_credentials_either`: status-remotes ebenso.
   - `plain_urls_stay_the_same`: URLs ohne Kontodaten unverändert.
4. Klasse `CheckApiTest` (Low→Umsetzung: API-Basis-Validierung):
   - `official_and_local_apis_are_accepted`: https://api.github.com,
     http://127.0.0.1:8000 (lokaler Fake-Server ist erlaubt), https://…/api
     ohne Ausnahme.
   - `bad_schemas_missing_hosts_and_control_chars_are_refused`: ftp://,
     "not-a-url", "https://" (kein Host), URL mit Steuerzeichen →
     ValueError mit verständlicher Meldung.
   (Der Web-Handler `settings` erfüllt die Anforderung, solange er
   `check_api` bei der Aktion „settings“ anwendet und bei Ungültigkeit
   nichts persistiert; ein eigener Browser-Fall dafür wurde bewusst
   weggelassen, weil der Unit-Test die Funktion direkt prüft.)

### Geänderter Browser-Test (tests/browser/test_ap06_github_ui.py)

- `test_merge_request_asks_confirm_and_only_then_sends_action`
  (Ersetzt den vorherigen sofort-Aktionstest; F11-askInline-Muster —
  inline Bestätigungsgruppe `.confirm` bzw. `role=group`):
  Vorbedingung: aktiviertes Projekt. Aktionen: 1. Klick Merge-Request →
  Erwartet: inline Bestätigungsgruppe (`.confirm`/role=group) mit
  „Ja"/„Abbrechen" sichtbar; Fake-API ohne POST /pulls; keine
  Fehlermeldung (kein Toast). 2. „Abbrechen" →
  Gruppe weg, Fake-API bleibt ohne Aktion, kein Toast. 3. Erneut +
  „Ja" → Erst JETZT sichtbare Fehlermeldung (kein Token in der
  Dashboard-Umgebung), Fake-API weiterhin ohne POST /pulls, Dashboard
  stabil.
  Hinweis: Der positive Durchlauf mit gültigem Token ist in der
  Testumgebung ausdrücklich nicht möglich (der Dashboard-Prozess hat
  keinen Token). Der Nachweis „Aktion nur nach Bestätigung" stützt
  sich auf vor der Bestätigung niemals gesendete Aktionen plus die
  erst nach Bestätigung sichtbar eintretende Verarbeitung.

### Rotphase (tatsächlich ausgeführt)

- Unit-Suite: `python3 -m unittest tests.unit.test_ap06_github -v` →
  `Ran 43 tests in 10.317s — FAILED (failures=5, errors=7)`, Exit-Code 1.
  Rotbilder: `CheckApiTest` (7 Subtest-ERRORs: `check_api` fehlt →
  `AttributeError`), `DefaultBaseTest.test_pr_without_base_names…` und
  `…unknown_default_base…` (FAIL), `ImportCollisionTest.
  concurrent_ticket_change…` (FAIL), `RemotesMaskingTest.
  remotes_masks…/status_never…` (FAIL). Bemerkung:
  `default_base_resolves_the_branch_name_of_origin_head` steht bereits
  grün — der Produktcode enthält `default_base` offenbar schon in der
  erwarteten Form; die restlichen Default-Basis-Aspekte sind rot.
  Alle 33 alten Tests blieben grün.
- Browser-Suite: `python3 -m unittest tests.browser.test_ap06_github_ui -v` →
  `Ran 6 tests in 7.391s — FAILED (errors=1)`, Exit-Code 1; der neue
  `test_merge_request_asks_confirm_and_only_then_sends_action` scheitert
  korrekt mit `TimeoutError` beim Warten auf die Bestätigungsgruppe
  (`.confirm`/`role=group`), weil die aktuelle Oberfläche unmittelbar
  sendet. Die 5 übrigen Browser-Fälle bleiben grün.

### Nächste Schritte

Der Coding-Agent implementiert die Review-Befunde kleinstmöglich;
danach beide Testbefehle erneut ausführen (Grünphase). Geändert wurden
nur Testdateien; keine Implementierungsdateien, keine Git-Operationen,
kein Token-Literal über 15 Zeichen im Report.

- Grünphase Runde 1: Die fünf Review-Verhaltensweisen sind implementiert und
  die neugeschriebenen Testfälle laufen jetzt grün (43 Unit-OK, 6 Browser-OK). Eine
  Naht-Anpassung im Kollisions-Test war dazu nötig: mein Aufräumen des
  Speichers-Seam patchte das ALIAS-Modulobjekt (`vibe_storage_under_test`),
  während `bin/vibe_github.py` die gemeinsame Storage-Schicht regulär über
  ``sys.modules["vibe_storage"]`` einbindet — der Eingriff erreicht den
  tatsächlich gebundenen Pfad. Fix im Test: `collision()` patcht jetzt
  `self.gh.vibe_storage.read_snapshot` (Fallback wäre der Loader-Alias),
  der Passthrough und die „AP9 Eingriff“-Sequenz (Schreibaufruf nach dem
  ersten Snapshot, vor dem Schreiben des Imports) bleiben logisch identisch.
  Reihenfolge dokumentiert: `read_snapshot` kann vom Modul für den Lese-
  schritt und darunter von `write_text` nochmals aufgerufen werden; der
  Side-Effect greift nur nach dem ERSTEN Aufruf und nur wenn ein späterer
  Schreibaufruf folgt. Danach:
  `python3 -m unittest tests.unit.test_ap06_github -v` → `Ran 43 tests in
  13.027s — OK`, Exit-Code 0 (`/tmp/opencode/ap6-review1-seamfix.log`);
  `python3 -m unittest tests.browser.test_ap06_github_ui -v` →
  `Ran 6 tests in 2.520s — OK`, Exit-Code 0
  (`/tmp/opencode/ap6-review1-browser-green.log`, inkl. des zweistufigen
  Merge-Request-Tests); `python3 scripts/check-no-secrets.py` →
  `OK: keine Geheimnisse erkannt.`, Exit-Code 0.

## Push-Aktion (Review Runde 1)

Der Reviewer markierte „Alle Git-Verwaltungsfunktionen in UI" als NOT
VERIFIED, weil es keinen isolierten Push gibt. Neue Testfälle — vor der
Implementierung geschrieben (Rotphase), nur in meinen Testdateien.

### Neue Unit-Tests (tests/unit/test_ap06_github.py, Klasse `CliPushTest`)

Vorbedingung jeweils: Projekt-Fixture mit cli-Sandbox; `run_push()` ruft
`cmd_github("proj", "push", out=stdout)` unter umgeleiteter Ausgabe auf und
behandelt `SystemExit` (Exit-Code wird konvertiert, 0 bleibt 0).

1. `test_cli_push_publishes_the_pending_commit_to_origin`
   - Vorbedingung: origin (file:// Bare-Repo) gesetzt, main bereits
     gepusht, danach ein zusätzlicher lokaler Commit („AP6: push
     sichtbar"), der origin noch nicht kennt.
   - Aktion: `run_push()`.
   - Erwartet: Exit-Code 0; Ausgabe enthält „übertragen" und „origin";
     `ls-remote origin refs/heads/main` zeigt exakt die lokale HEAD-SHA —
     der offene Commit wurde wirklich übertragen, nicht nur behauptet.
   - Fehlerfall: Exit-Code ungleich 0 oder origin unverändert → FAIL.
2. `test_cli_push_without_any_remote_reports_the_problem`
   - Vorbedingung: Projekt ohne konfiguriertes Remote.
   - Aktion: `run_push()`.
   - Erwartet: Exit-Code 1; Ausgabe enthält „Remote" (Kernphrase der
     verständlichen Fehlermeldung).
   - Fehlerfall: Exit 0 ohne Remote oder Meldung ohne „Remote" → FAIL.

### Neuer Browser-Test (tests/browser/test_ap06_github_ui.py, GitHubCardUiTest)

`test_push_action_is_available_and_reports_without_remote`
- Vorbedingung: aktivierte Karte („gh-demo"); zum Start kein Toast.
- Aktion: Zählen der Knöpfe mit Textbaustein „Push"; danach Klick.
- Erwartet: genau ein Push-Knopf in der Karte; nach dem Klick erscheint
  ein sichtbarer Toast, dessen Text „Remote" oder „Fehler" nennt; Karte
  und Push-Knopf bleiben danach bestehen (keine Zerstörung des Panels).
  Im Browser-Harness existiert schlicht kein origin — die erwartete
  Meldung ist daher „Kein Remote konfiguriert" (regex „Remote|Fehler").
  Ein positiver Push-Durchlauf im Browser würde einen echten lokalen
  origin brauchen und ist hier bewusst nicht Teil des Falls; aussagekräftige
  Nachweise für den eigentlichen Transfer liegen im Unit-Test.
- Fehlerfall: kein Push-Knopf (0), mehrfach Knöpfe, kein Toast oder
  Karte weg nach Klick → FAIL.

### Rotphase (tatsächlich ausgeführt)

- Unit: `python3 -m unittest tests.unit.test_ap06_github -v` →
  `Ran 45 tests in 12.668s — FAILED (errors=2)`, Exit-Code 1.
  Protokoll: `/tmp/opencode/ap6-push-unit-red.log`. Beide `CliPushTest`-
  Fälle scheitern korrekt: `ValueError: Aktion unbekannt: "push"
  (status|link|unlink|branches|fetch|pull|issues|issues-import|pr)` in
  `bin/vibe` (`cmd_github`, Zeile 1130) — die CLI-Aktion „push" fehlt.
  Die 43 übrigen Tests blieben grün.
- Browser: `python3 -m unittest tests.browser.test_ap06_github_ui -v` →
  `Ran 7 tests in 2.654s — FAILED (failures=1)`, Exit-Code 1. Protokoll:
  `/tmp/opencode/ap6-push-browser-red.log`. Der neue Fall scheitert an
  `AssertionError: 0 != 1` beim Push-Knopf (`push.count()`), die Karte
  kennt aktuell keine Push-Aktion. Die 6 übrigen Fälle blieben grün.
  (Vorsorglich bemerkt: ein erster Zwischenlauf des Browser-Tests
  schlug technisch fehl, weil die neue Methode hinter den
  `__main__`-Block geraten und gar nicht gesammelt worden war; die
  korrigierte Position ergab den oben dokumentierten echten Rotnachweis.)
- Nachahmen nicht möglich: Die Produktänderung (CLI-Aktion push,
  Web-API action=push, UI-Knopf „Push (Branch nach origin)") ist Sache
  des Coding-Agenten; danach beide Befehle erneut ausführen (Grünphase).

Geändert wurden nur `tests/unit/test_ap06_github.py`,
`tests/browser/test_ap06_github_ui.py` und dieser Report; keine
Implementierungsdateien, keine Git-Operationen, Ticket/Manifest unberührt.

### Fixlauf Push-Browser-Test

Ursache des Rotstandes war meine falsche Vorbedingung im Browser-Test
`test_push_action_is_available_and_reports_without_remote`: der
Testharness erzeugt das Projekt „gh-demo" bewusst MIT echtem lokalem
origin (file://); der Klick auf den Push-Knopf ist also eine reale
Erfolgsaktion, während mein Assert „Remote|Fehler" verlangte —
rot aus falscher Annahme, nicht aus einem Produktdefekt. Änderung:
der Test heißt jetzt `test_push_transfers_the_current_branch_to_origin`,
legt selbst einen Commit an, den origin noch nicht kennt
(„AP6: Browser-Push-Probe"), und stärkt die Behauptung auf den
positiven Nachweis: Toast enthält „übertragen" und „origin", und
`ls-remote origin refs/heads/main` zeigt exakt die lokale HEAD-SHA
(echter Transfer-Nachweis, analog zum Unit-Test). Der
Negativpfad (ohne Remote) bleibt im Unit-Test `CliPushTest` abgedeckt.
Ergebnis: `python3 -m unittest tests.browser.test_ap06_github_ui -v` →
`Ran 7 tests in 3.155s — OK`, Exit-Code 0
(`/tmp/opencode/ap6-push-browser-green.log`); `python3 -m unittest
tests.unit.test_ap06_github -v` → `Ran 45 tests in 12.392s — OK`,
Exit-Code 0 (`/tmp/opencode/ap6-push-unit-green.log`);
`python3 scripts/check-no-secrets.py` → OK, Exit-Code 0.

## Review Runde 2 (CHANGES REQUIRED → drei Produktverhaltensweisen)

Datum: 2026-11-09. Testfälle zuerst geschrieben, Rotphase echt ausgeführt;
die Implementierung folgt durch den Coding-Agenten. Testbefehle unverändert:

```
python3 -m unittest tests.unit.test_ap06_github -v
python3 -m unittest tests.browser.test_ap06_github_ui -v
```

### Neue Unit-Testfälle (tests/unit/test_ap06_github.py)

1. Klasse `GithubSlugDotNameTest` (R2-1/Medium, Akzeptanz: Verknüpfung
   gelingt vollständig; Naht `parse_remote_url`/`_repo_slug`):
   - `test_repo_names_with_dots_are_accepted_in_url_and_scp_form`
     Vorbedingung: Modul geladen. Aktion: `parse_remote_url` für
     `https://github.com/owner/my.repo.git`, `https://github.com/owner/my.repo`,
     `git@github.com:owner/my.repo.git`. Erwartet: Slug `owner/my.repo`
     (Punkt im Namen bleibt, `.git`-Suffix entfällt). Fehlerfall:
     ValueError/None → FAIL.
   - `test_dot_and_dotdot_path_segments_stay_refused` (Regressionswächter,
     heute bereits grün): `https://github.com/owner/../name`,
     `https://github.com/owner/./name`, `https://github.com/./name` →
     verständlicher `ValueError` (Meldung nicht leer).
   - `test_dotless_slugs_still_resolve_as_before` (Regressionswächter):
     `https://github.com/owner/name.git` → `owner/name`.
2. Klasse `LinkDotSlugTest` (R2-1/Medium über die CLI-Aktion `link`):
   - `test_link_with_dotted_repo_name_persists_the_full_slug`
     Vorbedingung: Projekt mit project.env (TYPE/TESTER/SANDBOX), kein
     origin. Aktion: `cmd_github("proj","link","https://github.com/owner/my.repo.git")`.
     Erwartet: Remote origin exakt auf die URL gesetzt; `GITHUB_ENABLED="1"`
     UND `GITHUB_REPO="owner/my.repo"` in `.vibe/project.env`; alle
     vorherigen env-Zeilen bleiben (Zeilenzählung `TESTER=` unverändert).
   - `test_link_refuses_dotdot_path_segments_without_any_change`
     (Regressionswächter): link mit `.../owner/../name` und
     `.../owner/./name` → Remote-Liste und project.env byteidentisch zum
     Vorher, lautes Verweigern (ValueError/SystemExit zulässig).
3. Klasse `DefaultBaseAfterLinkTest` (R2-2/Medium, Akzeptanz: Nach purem
   `link` MUSS origin/HEAD existieren; Merge-Request ohne --base sendet
   „main"):
   - Fixture: Bare-Repo `git init -b main`; origin via
     `git remote add origin file://...` (bewusst NICHT via clone — so ist
     origin/HEAD garantiert nicht gesetzt; experimentell verifiziert:
     `push -u` schreibt nur `refs/remotes/origin/main`, nie origin/HEAD);
     `push -q -u origin main`. Fixture-Invariante im setUp:
     `symbolic-ref refs/remotes/origin/HEAD` scheitert und
     `default_base` liefert "" — beide Assertionen laufen in Rot- UND
     Grünphase und belegen die Vorbedingung.
   - `test_link_establishes_origin_head_and_default_base_is_main`
     Aktion: `cmd_github("proj","link","file://<bare>")`. Erwartet:
     `symbolic-ref refs/remotes/origin/HEAD` rc 0 mit
     `refs/remotes/origin/main`, `vibe_github.default_base(project)` → "main".
   - `test_cli_merge_request_without_base_sends_main_and_succeeds`
     Aktion: link + `set_env_values(GITHUB_REPO/GITHUB_API lokal Fake-
     Server)` + `github_pr("proj", title=…, base=None, confirm=True)` mit
     `GITHUB_TOKEN="t-nur-test"` in der Prozessumgebung (github_pr löst den
     Token ausschließlich über die Umgebung auf). Erwartet:
     `{ok: True, base: "main", number: 42, url mit pull/42}`; die Fake-API
     erhielt POST /repos/owner/name/pulls mit `base == "main"` (keine SHA).
   - `test_cli_pr_flow_does_not_end_in_the_base_dead_end`
     Aktion: derselbe Zustand; `cmd_github("proj","pr",base=None,…,confirm=True)`
     mit umgeleiteter Ausgabe. Erwartet: KEIN SystemExit (die Sackgasse
     „Basis-Branch (base) unbekannt" wäre als sys.exit sichtbar); Ausgabe
     enthält „Merge-Request erstellt" und „pull/42".
4. Klasse `LinkMessageMaskingTest` (R2-3/Minor):
   - `test_link_success_message_masks_embedded_credentials`
     Vorbedingung: Projekt ohne origin. Aktion:
     `cmd_github("proj","link","https://v-kl:pw7@github.com/owner/repo.git")`
     (kurze Fake-Kontodaten < 16 Zeichen wegen check-no-secrets-Heuristik)
     mit umgeleiteter Ausgabe. Erwartet: Ausgabe enthält „Verknüpft",
     NIEMALS `v-kl`/`pw7` im Klartext, aber erkennbar „https://",
     „github.com/owner/repo" und das Maskenmuster `***` (Muster aus
     RemotesMaskingTest). Fehlerfall: Klartext in der
     `line("Verknüpft: …")`-Ausgabe → FAIL.

### Neue Browser-Testfälle (tests/browser/test_ap06_github_ui.py)

1. `GitHubCardUiTest.test_github_link_button_keeps_dot_in_the_repository_name`
   (R2-1/Medium über die UI):
   Vorbedingung: eigenes Projekt `gh-dot` (Fixtures gh-demo/gh-off bleiben
   unberührt; keine bestehenden Tests abgeschwächt). Aktion: Repo-Feld der
   Git & GitHub-Karte auf `owner/my.repo`, Klick „Mit GitHub verknüpfen".
   Erwartet: env-Datei erhält ohne manuelles Nachladen
   `GITHUB_REPO="owner/my.repo"` und `GITHUB_ENABLED="1"`; Karte bleibt
   sichtbar. In der Rotphase zeigt der Toast die Absage
   `GitHub-Repository: owner/name erwartet (z. B. owner/name.git)`.
2. Neue Klasse `LinkOnlyMergeRequestUiTest` mit EIGENEM Dashboard-Prozess
   (R2-2/Medium über den UI-Klick-Fluss):
   - Harness wie GitHubCardUiTest, aber mit `GITHUB_TOKEN="t-nur-test"` in
     der Prozessumgebung des Dashboards — sonst erreicht der Fluss die
     Basis-Verarbeitung gar nicht (Token-Prüfung kommt zuerst) und der
     Review-Befund wäre statisch unsichtbar. Die bestehende Klasse
     `GitHubCardUiTest` bleibt absichtlich ohne Token (ihre Token-
     Fehlermeldungs-Tests blieben unverändert grün).
   - Vorbedingung: Projekt `gh-linkonly`, origin via `git remote add
     origin file://<bare, mit -b main>`, `push -u origin main`, kein
     origin/HEAD.
   - `test_merge_request_after_link_only_sends_default_base`
     Aktionen: (a) Karten-Speichern mit Repo `owner/name` und lokaler
     Fake-API-Basis (env-Nachweis `GITHUB_API="http://127.0.0.1:…"`);
     (b) reine link-Aktion über die produktgleiche Web-API-Naht
     `POST /api/github {action:"link"}` mit `file://`-URL — bewusst nicht
     über den Karten-Link-Knopf: dieser baut zwangsweise
     `https://github.com/<repo>.git`-URLs, und der Merge-Request-Push würde
     dann echten Netzkontakt zu github.com versuchen (Testverbot; im
     Debuglauf sichtbar über den ksshaskpass-Fehler). Die Naht
     `vibe.github_link` ist für Karten-Knopf und Web-API identisch;
     (c) Ansicht wie nach einer Erfolgsaktion neu aufgebaut
     (`page.reload()`, Merge-Request-Knopf sichtbar); (d) Klick auf
     „Merge-Request stellen" + inline „Ja, stellen".
     Erwartet: Fake-API erhält POST /pulls mit `base == "main"`; Meldungen
     enthalten „Merge-Request", NIE „Basis-Branch (base) unbekannt"; Karte
     bleibt sichtbar. In der Rotphase erscheint exakt die Sackgasse
     „Basis-Branch (base) unbekannt: angeben oder origin/HEAD setzen".
   - Neue Hilfsfunktionen `wait_for_toast`/`wait_for_toast_scan`: Toasts
     verschwinden automatisch nach ca. 8 s; es wird auf Text gewartet
     bzw. der Verlauf gesammelt (Race-robust; keine Assertions weicher).

### Rotphase (tatsächlich ausgeführt)

- Unit: `python3 -m unittest tests.unit.test_ap06_github -v` →
  `Ran 54 tests in 12.794s — FAILED (failures=3, errors=5)`, Exit-Code 1.
  Protokoll: `/tmp/opencode/ap6-r2-unit-red.log`.
  Rotstände (ausschließlich fehlende Verhaltensweisen, keine Testdefekte):
  - `GithubSlugDotNameTest.test_repo_names_with_dots…`: 3 subTest-ERROR mit
    `SystemExit: GitHub-Repository: owner/name erwartet (z. B.
    owner/name.git)` — Punkte-Slugs werden aktuell abgelehnt.
  - `LinkDotSlugTest.test_link_with_dotted_repo_name…`: ERROR mit derselben
    Absage (Remote/env bleibt unverändert — korrekt im Fehlerpfad, falsch
    im Erfolgsfall).
  - `DefaultBaseAfterLinkTest.test_link_establishes_origin_head…`: FAIL —
    nach link fehlt origin/HEAD.
  - `DefaultBaseAfterLinkTest.test_cli_merge_request_without_base…`:
    `GitHubError: Basis-Branch (base) unbekannt: angeben oder origin/HEAD
    setzen`.
  - `DefaultBaseAfterLinkTest.test_cli_pr_flow…`: SystemExit mit genau
    dieser Meldung — die Sackgasse verbatim.
  - `LinkMessageMaskingTest.test_link_success_message_masks…`: FAIL —
    Klartext `v-kl:pw7` in „Verknüpft: …".
  Alle 45 bestehenden Unit-Tests blieben grün; die drei
  Regressionswächter (`dot_and_dotdot…`, `link_refuses_dotdot…`,
  `dotless_slugs…`) sind grün und bleiben gefordert.
- Browser: `python3 -m unittest tests.browser.test_ap06_github_ui -v` →
  `Ran 9 tests in 40.000s — FAILED (failures=2)`, Exit-Code 1.
  Protokoll: `/tmp/opencode/ap6-r2-browser-red.log`.
  - `test_github_link_button_keeps_dot…`: kein Toast „Verknüpfung
    gespeichert"; zuletzt gesehen: `GitHub-Repository: owner/name erwartet
    (z. B. owner/name.git)`.
  - `test_merge_request_after_link_only_sends_default_base`: kein POST
    /pulls; Verlauf zeigt wiederholt die Sackgasse „Basis-Branch (base)
    unbekannt: angeben oder origin/HEAD setzen".
  Die 7 bestehenden Browser-Tests blieben grün.
- `python3 scripts/check-no-secrets.py` → OK, Exit-Code 0.

### Erwartbarer Grünstand nach der Implementierung

54 Unit-Tests OK und 9 Browser-Tests OK, je Exit-Code 0 — ohne Abschwächung
der ersten 45/7. Die drei ./..-Regressionswächter bleiben als Grünpflicht
bestehen.

### Vertragsnarben (Funktionsgrenzen, an die sich die Tests halten)

- `vibe_github.parse_remote_url(url)` ist die fachliche URL-Naht (R2-1):
  Rückgabe owner/name oder None; ValueError für die Ablehnung. Die
  Fix-Semantik liegt in `bin/vibe_github.py` (parse_remote_url/_repo_slug).
- `cmd_github(…, out=)` und `github_link(name, url)` sind die CLI-Naht
  für R2-1 und R2-3. Die Erfolgsmeldung „Verknüpft: …" war Teil des
  beobachteten Rohzustands (Klartext-Ausgabe).
- `vibe_github.default_base(project)` + `create_pull_request(…, base=None)`
  + `github_pr(confirm=True)` sind die Basis-Naht (R2-2). Der Test-Vertrag
  erwartet, dass die link-Verarbeitung selbst origin/HEAD schreibt (git-
  „remote set-head"/symbolic-ref sind Implementierungsdetails, Quelle ist
  die gleiche Naht für CLI und Web-API).
- Web: `/api/github` action=link ist dieselbe `github_link`-Naht — der
  Browser-Test treibt sie direkt, um das zwangsweise
  `https://github.com`-Umschreiben des Karten-Knopfs (und damit echten
  Netzkontakt beim PR-Push) zu vermeiden. Beobachteter UI-Klick-Fluss
  bleibt: Karten-Aktionen settings → link → „Merge-Request stellen" mit
  Inline-Bestätigung.
- Nicht per Browser getestet, dokumentiert: Web-msg-Maskierung
  („Verknüpfung gespeichert: <url>") — der UI-Link-Knopf kann strukturell
  keine Kontodaten erzeugen. Empfehlung an den Coding-Agenten:
  `vibe_github._mask_credentials` für die link-Erfolgsmeldungen
  (CLI „Verknüpft: …" und Web-msg) anwenden; PR `github_pr`-Meldungen
  enthalten schon ohnehin keine Remote-URL.

### Learnings (für künftige Rotphasen)

1. Toast-Lebensdauer (~8 s, Container `#toasts`): Toast-Assertions müssen
   auf Text warten bzw. den Verlauf sammeln; ein sofortiges
   `.first`-Read und ein nach 15-s-Polle nachgeholter Read liefern
   unterschiedliche Bilder. `wait_for_toast`/`wait_for_toast_scan` machen
   beide Stände umstellungsrobust beobachtbar (keine weicheren Assertions).
2. Kartenzustand nach API-Aktionen: Der Merge-Request-Knopf rendert nur
   im aktivierten Zustand (`active? prBtn : null`). Nach einem link von
   außerhalb des Karten-Handlers muss die Ansicht neu aufgebaut werden,
   sonst Timeout auf einen bewusst fehlenden Knopf.
3. Gefahrenstelle in der echten UI-Kette: der Karten-Link-Knopf
   überschreibt origin mit `https://github.com/<slug>.git`; ein danach aus
   der Karte ausgelöster Push des Merge-Request-Flusses versucht dann
   echten Netzzugriff (Rotlauf-Fehler ksshaskpass). UI-Ketten für den
   Merge-Request daher nur mit file://-Remotes treiben (Testordnung
   „keine echten externen Dienste"); der echte github.com-Pfad bleibt über
   den lokalen Fake-API-Server auf Unit-Ebene nachgewiesen.
4. Token-Struktur im Dashboard: Die bestehende Browser-Klasse läuft ohne
   Token (weshalb dort nur der VOR-Confirm-Nachweis möglich ist). Der
   Nachweis für die Basis-Verarbeitung brauchte die neue Klasse mit
   faken Token in der Prozessumgebung — als eigenes, isoliertes Setup,
   damit keine bestehende Isolation abgeschwächt wird.
