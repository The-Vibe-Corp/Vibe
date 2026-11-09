# AP6 — Vorbereitung für GitHub-Repo

Stand: 2026-11-09
Ticket: TICKETS.md AP6 („GitHub-Integration: Branches/Updates, Merge-Requests, Issues als Arbeitspakete“)
Arbeitsbranch: `vibe/vibe-AP6-1794238201536384312-14374-6010`

## Ziel

Ein Projekt kann optional und je Projekt entschieden mit einem GitHub-Repository
verbunden werden. Die Oberfläche bietet dann die Git-Verwaltung (Status,
Branches, Abrufen, Aufholen, Push), das Stellen von Merge-Requests und die
Übernahme von GitHub-Issues als Arbeitspakete mit Label-Filter und
konfigurierbarem Task-Label. Umsetzung als EIN Einzelfeature; ohne Verknüpfung
ändert sich die Oberfläche nicht.

Nicht im Umfang (SPEC): kein automatischer Push, Merge oder Release. Jede
Netzaktion außer dem Lesen von Status/Branches ist eine bewusste
Nutzerentscheidung (Klick im Dashboard, CLI-Aufruf mit Bestätigung).

## Konfiguration

Je Projekt in `.vibe/project.env`:

- `GITHUB_ENABLED` — „1“ schaltet GitHub für das Projekt ein (Standard aus).
- `GITHUB_REPO` — `owner/name`; nur diese Form gilt als GitHub-Repository.
- `GITHUB_LABEL` — Task-Label für Issues (Standard `vibe`).
- `GITHUB_API` — API-Basis (Standard `https://api.github.com`); überschreibbar,
  damit Prüfungen gegen einen lokalen Scheindienst laufen können.

Der Access-Token kommt ausschließlich aus der Umgebung (`GITHUB_TOKEN` oder
`GH_TOKEN`). Er wird nie gespeichert, geloggt oder in Fehlermeldungen
übernommen; ohne Token enden Netzaktionen mit einer verständlichen Meldung
(„Kein GitHub-Zugangstoken …“).

## Umsetzung

### Modul `bin/vibe_github.py`

Fachmodul, Standardbibliothek, keine neuen Abhängigkeiten:

- `read_config` — sichere Defaults; GitHub bleibt bis zur Konfiguration aus.
- `git` — alle Git-Aufrufe mit Argumentliste (keine Shell, `core.fsmonitor` aus).
- `remotes`, `current_branch` — Lesezustand.
- `status` — Verknüpfung, Branch, Remotes, Ahead/Behind, `unpushed`.
- `branches` — lokale Branches mit aktuell-Flag und Abstand.
- `fetch` — `git fetch --all` (kein Merge).
- `pull` — `git pull --ff-only`; divergente Zustände werden abgelehnt, der
  lokale Stand bleibt intakt.
- `push` — bewusster Push eines Branches mit Upstream-Setzung.
- `list_issues` — offene Issues mit Label-Filter über `GITHUB_API`.
- `create_pull_request` — Merge-Request (head/base, Basis ermittelt aus
  origin); nur mit ausdrücklicher Bestätigung (`confirm` bzw. CLI `--confirm`).
- `import_issues_into_tickets` — übernimmt Issues mit dem konfigurierten Label
  als `- [ ] GH-<Nr> <Titel>` in TICKETS.md; idempotent (vorhandene
  `GH-<Nr>`-Nummern werden übersprungen) und atomar (mkstemp + os.replace).

Ahead/Behind rechnet gegen die **aktuelle** Fern-Referenz via `git ls-remote`,
nicht gegen veraltete `origin/<branch>`-Referenzen. Ist das Fern-Objekt lokal
unbekannt, zieht `_push_state` gezielt nur dieses Objekt nach
(`git fetch origin <sha>`): ohne Merge, ohne Verschieben von Fern-Referenzen.
Scheitert der Nachzug, bleibt der Stand bei 0/0 statt einer halben Angabe.

Bekannte Git-Grenze: `rev-list <branch>...<sha>` scheitert mit rc 128
(„Invalid symmetric difference expression“), wenn das SHA-Objekt lokal fehlt —
deshalb der geschilderte Objekt-Nachzug. Ohne lokales Objekt lässt sich der
Abstand schlicht nicht korrekt berechnen.

### CLI `bin/vibe`

`vibe github <projekt> <status|link|unlink|branches|fetch|pull|push|issues|issues-import|pr>`.
`link` prüft die Adresse über `parse_remote_url`: github.com verlangt
`owner/name`, Git-Remotes anderer Hosts bleiben zulässig (dann Status,
Branches und Push, aber ohne Issues/Merge-Request). Alle Aktionen sind
bewusste Nutzerentscheidungen; der Merge-Request braucht zusätzlich `--confirm`.

### Web-API `bin/vibe-web.py`

`POST /api/github` mit den Aktionen `settings`, `link`, `unlink`, `fetch`,
`pull`, `push`, `issues`, `import`, `pr`; `pull` läuft mit `--ff-only`, der
Merge-Request braucht `confirm: true` im Body. Die API-Basis wird bei der
Aktion `settings` über `check_api` geprüft (http/https mit Host, keine
Steuerzeichen). Der Pfad ist in der V-004-Route-Whitelist; alle anderen
Transportregeln gelten unverändert.

### Oberfläche `bin/web/app.js`, `bin/vibe_services.py`

`vibe_services.project_detail` liefert `github` (Status und Branches, bei
Fehlern degradiert). Im Einstellungen-Tab des Projekt-Details liegt die Karte
„Git & GitHub“: Eingaben (Aktiv, Repo, Label, API), Speichern, Verknüpfen,
Lösen, Branchliste mit Ahead/Behind sowie die Aktionen Abrufen (fetch, ohne
Merge), Push (Branch nach origin), Pull (aufholen, `--ff-only`),
Merge-Request stellen (mit Bestätigung im F11-Inline-Pattern), Issues laden
und Import. Ohne Aktivierung zeigt die Karte eine klare Hinweismeldung und
bietet keinen Merge-Request. Bewusste Abgrenzung: ein Branchwechsel als
Laufaktion bleibt absichtlich draußen — der Paket-Läufer arbeitet in eigenen
Worktrees; Einträge in der Branchliste sind Leseansicht.

## Tests und Prüfungen

### Test-Agent (verbindliche Tests)

`tests/unit/test_ap06_github.py` (54 Tests) und
`tests/browser/test_ap06_github_ui.py` (9 Playwright-Tests) stammen vom
Test-Agenten. Fallbeschreibung, dokumentierte Rote Phase und die späteren
Green-Läufe sind in `docs/reviews/AP6-test-agent-report.md` erfasst. Die
Browser-Tests laufen gegen ein echtes Dashboard und einen lokalen
Fake-GitHub-Server; Fehlerfälle prüfen, dass der Access-Token in keiner
Meldung erscheint.

### Testdefekte und Fixläufe des Test-Agenten

Der Test-Agent korrigierte nur eigene Testdateien (Details im Report,
Abschnitt „Fixlauf“):

1. CRLF-Test liest jetzt Bytes (`read_bytes`): der Textkanal normalisiert
   Universal-Newlines, ein CRLF-Nachweis bleibt sonst unmöglich.
2. `make_bare()` nutzt `git init --bare -b main`: in isolierter Umgebung
   (`GIT_CONFIG_GLOBAL=/dev/null`) wäre der Bare-Default `master`; das
   verursachte die RemoteOps-ERRORs vor jeder Produktausführung.
3. `test_pull_absorbs_remote_updates`: vergessener Push des Kollaborators
   ergänzt.
4. Fake-Token-Literal auf 9 Zeichen gekürzt: die Secret-Heuristik
   (Zuweisungs-Literal ≥ 16 Zeichen) schlug sonst zu Unrecht an; die
   AssertionError-Präzision blieb exakt.
5. `tests/unit/test_setup_vibe.py` und `tests/unit/test_install_lifecycle.py`:
   die dortige PROGRAM_FILES-Abbildung bzw. Kit-Fixture enthält
   `vibe_github.py` jetzt, weil der Installer das neue Modul mitkopiert
   (V-021-Muster).

### Prüfresultate (tatsächlich ausgeführt)

- `python3 -m unittest tests.unit.test_ap06_github` — 54 Tests, OK.
- `python3 -m unittest tests.browser.test_ap06_github_ui` — 9 Tests, OK.
- `python3 -m unittest tests.unit.test_baseline_inventory tests.unit.test_setup_vibe tests.unit.test_install_lifecycle` — OK.
- `bash scripts/verify.sh quick` — Exit 0 (Manifest, Syntax, Geheimnisprüfung).
- `bash scripts/verify.sh full` — Exit 5 nur mit paketfremden Abweichungen
  (Endstand, Protokoll `/tmp/opencode/ap6v/vibe-verify-6tesqvjg/verify.log`,
  Aufbau unter kurzem `TMPDIR`, damit tmux-Sockets unter die Pfadgrenze
  fallen; Endstand 1226 Tests):
  1. `test_real_sandbox_allows_write_dirs_and_denies_unlisted_paths`
     (HOME_OPEN, /tmp read-only) — schon am unveränderten Ausgangsstand
     `f44d8d6` (Klonkopie `/tmp/opencode/ap6-base`) identisch vorhanden;
     Umgebungs-/Flake-Verhalten, wie in `docs/reviews/B4-review-1.md`
     dokumentiert.
  2. `test_dry_run_explains_pi_and_its_install_command` (AP04-Pi-Hinweis)
     und `test_repository_content_has_no_personal_home_paths_or_secrets`
     (Home-Pfade in Altdokumenten) — die in TICKETS.md Nachbarpaketen
     dokumentierten Dauer-Failures, paketfremd.
  Ohne `TMPDIR`-Verkürzung schlagen zusätzlich tmux-abhängige Lebenszyklus-,
  Sandbox- und Dashboard-Tests wegen „File name too long“ für den Socket im
  langen Sandbox-Pfad fehl (36 Fehlschläge + 2 Fehler in 1217, Endstand 1226); unter kurzem
  `TMPDIR` ist `tests.unit.test_lifecycle` 17/17 OK — Umgebungsgrenze der
  Prüfumgebung, kein AP6-Regress. Alle AP6-Anteile (Manifestabgleich,
  Installationsmodule, Baseline-Doku) sind damit bestätigt.

### Review Runde 1 und 2 (Nacharbeiten, vom Test-Agenten getestet)

- Runde 1 (CHANGES REQUIRED, `docs/reviews/AP6-review-1.md`; die Datei
  enthält Übertragungsartefakte des Reviewmodells und bleibt per
  Verbatim-Regel unverändert — ihr Inhalt wurde vollständig durch Runde 2
  nachgeprüft): PR-Default-Basis (`default_base` über symbolic-ref),
  zweistufige Merge-Request-Bestätigung in der UI (askInline),
  Import-Kollisionserkennung über `vibe_storage`, Maskierung von
  Remote-Zugangsdaten in Ansichten, `check_api`-Validierung,
  `per_page`-Grenze dokumentiert, ls-remote-Doku, Aktionslisten inkl. `push`,
  geschlossener HTTPError, isolierter Push in UI/CLI.
- Runde 2 (`docs/reviews/AP6-review-2.md`, CHANGES REQUIRED): drei
  behobene Befunde — Repo-Namen mit Punkt jetzt erlaubt
  (`owner/my.repo`; `.`/`..` bleiben abgelehnt), `link` versorgt
  `refs/remotes/origin/HEAD` gleich mit (beste Bemühung; der bestätigte
  Merge-Request versucht es einmal nach, wenn die Basis unbekannt blieb),
  link-Erfolgsmeldungen (CLI/Web) maskieren eingebettete Zugangsdaten.
  Testschritt dokumentiert im Test-Agent-Report, Abschnitt „Review Runde 2“:
  Endstand 54 Unit- + 9 Browser-Tests, grün.
- Runde 3 (`docs/reviews/AP6-review-3.md`): **Verdict PASS** (0 Critical/
  High/Medium; 1 Minor — veraltete Zeilenreferenzen in docs/baseline.md,
  rein dokumentarisch durch Symbolnamen-Nennung behoben, keine
  Codeänderung).

## Manifest

`docs/import-manifest.json`: neuer Eintrag `bin/vibe_github.py`, neue SHA-256
für die geänderten Programmdateien und `scripts/setup-vibe.py`,
`aenderungen`-Eintrag AP6 (2026-11-09), `stand` 2026-11-09.

## Grenzen und bewusste Abgrenzungen

- Alle Git-Verwaltungsfunktionen anzeigen, einstellen und bewusst ausführen
  sind in der Karte möglich (Status, Branchliste, Fetch, Push, Pull,
  Merge-Request, Issues, Import). Ein Branchwechsel als laufende Aktion ist
  bewusst nicht Teil der Oberfläche: der Paket-Läufer arbeitet je Paket in
  eigenen Worktrees; die Branchliste ist eine Leseansicht mit Ahead/Behind.
- Issue-Listing holt mit `per_page=100`; Repos mit mehr als 100 offenen
  (labelgefilterten) Issues zeigt die erste Seite ohne Paginierung — die
  Begrenzung ist hier dokumentiert (im CLI- und UI-Kontext sind Label-Filter
  üblich, so dass die praktisch begrenzte Menge der Task-Issues im
  Vordergrund steht).
- Der GitHub-Dienst wird nur für Issues und Merge-Requests angerufen; der
  Status-/Branches-Abgleich nutzt den Git-Layer (`ls-remote`, gezielter
  Objekt-Nachzug), der mit den Projekt-Remotes arbeitet.
- Eingebettete Zugangsdaten in Remote-URLs werden in Status-/Branchansichten
  maskiert (`scheme://***@host/pfad`); die Remote selbst bleibt wirksam.
  Ein Access-Token wird vollständig aus der Umgebung gelesen.
- Die API-Basis darf http/https sein; `http:` sollte nur für lokale
  Scheindienste/Prüfungen genutzt werden.

## Trilium

Trilium-Eintrag: `RTYec92LsBSL` („AP6 Vorbereitung für github Repo“ im
Projektordner „vibe“ / „Features“); enthält die Prüfnachweise und wurde am
2026-11-09 um den Commitstand (`86e90d8`) und die Reviewrunden 1–3
(abgeschlossen mit PASS) ergänzt.
