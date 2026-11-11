# AP8 — Bereit für GitHub Teil 2: Projekt aus GitHub auschecken

Stand: 2026-11-11
Ticket: TICKETS.md AP8 („Vibe soll in der Lage sein, ein Projekt aus GitHub
auszuchecken und als neues Projekt im Projektordner anzulegen. In diesem
Projekt muss dann alles entsprechend der lokalen vibe-Einstellungen übernommen
werden. Die lokalen Einstellungen überschreiben die Projekteinstellungen. Die
im Projekt aktiven Agenten müssen auch lokal erneut auf die lokal
konfigurierten Agenten angepasst werden.“)
Arbeitsbranch: `vibe/vibe-AP8-1794350105884804023-2529435-12489`
Ausgangscommit: `8afde0e` (Prüfisolierung)

## Ziel

Ein Projekt kann aus einem Git-Remote (GitHub-URL oder beliebige Git-URL)
ausgecheckt und als neues Projekt im vibe-Projektordner angelegt werden.
Dabei gelten konsequent die lokalen vibe-Einstellungen des Nutzers, nicht die
im Repository mitgelieferten: Das Repository enthält nur Projektcode; die
vibe-Einstellungen sind je Nutzer und Instanz individuell (analog zur
Projektkonfiguration einer IDE). Diese Auslegung wurde mit dem Nutzer
abgestimmt (`vibe ask qdb119878f268`).

Nicht im Umfang: keine echten GitHub-Netzaufrufe in Tests, kein automatischer
Push/Merge, keine Änderung bestehender Projekte.

## Verhalten

### CLI `vibe clone <url> [name]`

- `url` — Git-Remote; GitHub-Form `https://github.com/owner/name.git` und
  beliebige Git-URLs (inklusive `file://`-Remotes für Tests) sind zulässig.
- `name` — optionaler Projektname; ohne Angabe wird er aus der URL abgeleitet
  (`_checkout_name`), Kollisionen im Projektordner sind ein Fehler.
- Ablauf: `vibe_github.clone(url, target)` checkt den Standard-Branch des
  Remotes in `VIBE/<name>` aus; bei Fehlschlag wird ein angelegtes
  Zielverzeichnis vollständig entfernt (kein halbes Projekt).
- Danach übernimmt `checkout_from_github` die lokale Ausrichtung
  (`_adopt_checked_out_project`) und meldet Projektname plus Zusammenfassung.
- Fehler werden als verständliche Meldung beendet (`sys.exit`), das Modul
  selbst wirft nur `ValueError`/`OSError`/`StorageError`.

### Übernahme der lokalen Einstellungen

- Fehlende Vorlagedateien (TICKETS.md, FEEDBACK.md, AGENTS.md, `.opencode/`,
  `.vibe/`) werden aus der lokalen Vorlage des erkannten Projekttyps ergänzt
  (`copy_tree`, `{{NAME}}` wird ersetzt); vorhandene Projektdateien bleiben
  unangetastet.
- `AGENTS.md` erhält die lokale Regelblock-Fassung (`ensure_general_rules`).
- Der Projekt-Test-Agent wird durch die lokale Test-Agent-Vorlage ersetzt
  (`_ensure_local_test_agent`) — die lokale Testverantwortung gilt.
- `.vibe/project.env`: Fehlt sie, wird sie aus der lokalen Vorlage des
  erkannten Typs angelegt (`_detect_project_type` über Datei-Marker).
  Existiert sie, werden nur abweichende verwaltete Schlüssel überschrieben
  (TYPE, REVIEWER, TESTER, SANDBOX, SANDBOX_TOOLS, VERIFY_QUICK,
  VERIFY_PACKAGE, VERIFY_FULL) — fremde Schlüssel des Projekts bleiben.
- GitHub-URLs setzen `GITHUB_REPO=owner/name` und `GITHUB_ENABLED=1`; die
  Verknüpfung benötigt keinen GitHub-REST-API-Aufruf und keinen Token
  (`git remote set-head origin --auto` fragt den Git-Remote selbst ab).
  Andere Git-URLs setzen keine GitHub-Schlüssel.
- `.vibe/agents.json`: Die im Projekt aktiven Agenten werden auf die lokal
  konfigurierten Agenten abgebildet (`_remap_project_agents`): nur Namen, die
  lokal existieren, bleiben aktiv; der Vibe-Agent bleibt immer aktiv;
  Modellangaben folgen den lokalen Einstellungen. Entfernte Agenten und
  Zuordnungen werden in der Zusammenfassung gemeldet.

### Web und Oberfläche

- `POST /api/clone` mit `{url, name?}` → `{ok, message, project}`;
  Fehler → `{ok:false, message}` (HTTP 400), Tokenpflicht wie überall.
- Dashboard, Tab Projekte: Karte „Neues Projekt“ mit URL-Feld (Platzhalter
  `https://github.com/owner/name.git`) und Knopf „Aus GitHub auschecken“.
  Erfolg: Meldung, Projektliste wird neu geladen, das Projektdetail öffnet
  sich; Fehler: klare Meldung, Karte bleibt nutzbar.

## Grenzen

- `clone()` nutzt `git clone` ohne Terminal-Prompt (`GIT_TERMINAL_PROMPT=0`);
  geschützte Remotes brauchen vorgelegte Zugangsdaten; die promptfreie
  Ausführung mit Credential-Injection folgt dem bestehenden AP6-Muster
  (`vibe_github.git`).
- Die Agentenabbildung ist namensbasiert; ein Projekt-Agent ohne lokales
  Pendant wird deaktiviert und gemeldet, nicht erfunden.
- Nachweis (Review-Runde 1, Info): Die bestehenden AP6-Funktionen `fetch`,
  `pull`/`merge` und `push` (`bin/vibe_github.py`) geben Git-Rohausgaben ohne
  `mask_embedded_credentials` zurück — derselbe Defekttyp wie der hier
  behobene, jedoch am Ausgangscommit bereits vorhanden und paketfremd. Als
  Follow-up erfasst; die drei Rückgabestellen sollten in einem eigenen
  Arbeitspaket ebenfalls maskieren.
- Tests arbeiten ausschließlich gegen `file://`-Bare-Repositories in
  temporären Umgebungen; keine echten GitHub-Aufrufe, keine Modellkosten.

## Prüfungen (tatsächlich ausgeführt)

- Unit: `tests/unit/test_ap8_github_checkout.py` — 33/33 OK
  (Test-Agent, siehe unten; enthält CLI-, Übernahme-, Fehler- und Cleanup-Fälle
  sowie Regressionstests der Review-Runde 1).
- Browser: `tests/browser/test_ap8_checkout_ui.py` — 4/4 OK (echtes Dashboard,
  Chromium headless): Karte, Auschecken mit Projektdetail-Öffnung,
  Fehlermeldung bei ungültiger URL, Tokenpflicht von `POST /api/clone`.
- `bash scripts/verify.sh quick` — OK (Manifest 57 Dateien, Syntax 129
  Python/8 Bash/4 JSON, keine Geheimnisse).
- `bash scripts/verify.sh full` — die AP8-bezogenen Prüfungen sind grün; vom
  Gesamtergebnis verbleiben 5 Failures, die am Ausgangscommit `8afde0e` in
  derselben Form paketfremd auftreten (Baseline-Vorhanden: ap04-Dry-Run,
  f27-Keep-Changes in drei Varianten, Home-Pfad-Test in docs/features/B4.md);
  weitere Baseline-Failures (feedback_entries, pi_agent_dir, real_sandbox)
  laufen umgebungsabhängig durch.

## Testherkunft

- Alle Tests stammen vom unabhängigen Test-Agenten (Konfiguration `TESTER`):
  `tests/unit/test_ap8_github_checkout.py`, `tests/browser/test_ap8_checkout_ui.py`,
  Bericht `docs/reviews/AP8-test-agent-report.md`.
- Fixlauf 1: Nach dem ersten Lauf meldete der Test-Agent einen
  Implementierungsdefekt (`POST /api/clone` antwortete im Erfolgspfad mit
  HTTP 500, `ok` war nicht gesetzt) — behoben in `bin/vibe-web.py`.
- Fixlauf 3: Regressionstests zu den Beanstandungen der Review-Runde 1
  (Maskierung von Zugangsdaten in Clone-Fehlermeldungen, verwaltete
  Schlüsselbegrenzung, Zielordner-Cleanup bei Übernahmefehlern) — 33 Tests.
- Fixlauf 2: Der Test-Agent stellte eine Kontamination in seiner eigenen
  Test-Infrastruktur ab (dauerhafte `os.environ`-Mutation von
  `VIBE_STORAGE_LOCK_DIR`/`VIBE_STATE` in `StorageFixture.setUp` ohne Rückbau;
  danach scheiterten nachgelagerte Storage-/Write-Dirs-Tests an geleakten
  Pfaden). Behoben durch `mock.patch.dict` mit automatischem Rückbau; der
  kombinierte Lauf (AP8 + Storage + Write-Dirs, 80 Tests) ist grün. Die
  Coding-Seite hat die Testdatei nicht verändert.

## Nachweise

- Manifest: `docs/import-manifest.json` — Einträge AP8 (Datum 2026-11-11),
  SHA-256/Größe von `bin/vibe`, `bin/vibe-web.py`, `bin/vibe_github.py`,
  `bin/web/app.js` aktualisiert; `python3 scripts/check-import-manifest.py` OK.
- Bestandsaufnahme: `docs/baseline.md` um `vibe clone`, `POST /api/clone` und
  die Auscheck-Karte ergänzt; `tests/unit/test_baseline_inventory.py` 8/8 OK.
- Review: `docs/reviews/AP8-review-1.md` (Runde 1, FAIL mit 1 Medium +
  3 Minor) und `docs/reviews/AP8-review-2.md` (Runde 2, Verdict: PASS);
  alle Runde-1-Befunde behoben, Regressionstests vom Test-Agenten.
- Trilium: Notiz „AP8 — Projekt aus GitHub auschecken“ unter Features/vibe
  (über Trilium-MCP angelegt).
