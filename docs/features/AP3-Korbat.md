# AP3-Korbat — GitHub-Issues-Unterstützung für über GitHub verwaltete Projekte

Stand: 2026-11-22
Branch: `feature/korbat/ap3-korbat` (Ausgangscommit `6449438`, B3-Commit
unangetastet auf demselben Branch)
Spezifikation: TICKETS.md AP3-Korbat; zusätzliches Nutzer-Addendum (verbindlich):
Tickets werden erst dann automatisch in Läufen bearbeitet, wenn sie zur
Bearbeitung freigegeben sind — ansonsten bleiben sie Entwürfe (Drafts).
Umfang: bidirektionale Issue-Synchronisation (Opt-in je Projekt),
Draft/Ready-Freigabemodell, drei Ticketzustände, Assignee-Filter,
PR-Abschluss über `Closes #<n>`, Kategorieauswahl Bug/Feature,
Backbone-UI-Trennung, Nova-Oberfläche.

---

## 1. Zusammenfassung

Arbeitspakete, Bugs und Feedback waren bisher rein lokale Markdown-Dateien
(`TICKETS.md`/`FEEDBACK.md`); GitHub war nur für Branches und Merge-Requests
verknüpft, und der bisherige Import (`issues-import`) war eine Einbahnstraße.
AP3-Korbat macht GitHub Issues für verknüpfte Projekte zur führenden Quelle
(single source of truth) — als ausdrückliches Opt-in pro Projekt:

1. **Sync (Button/CLI, Pull+Push+Close in einem Aufruf):** offene Issues
   erscheinen als lokale Blöcke (`GH-<n>`); lokal angelegte Tickets ohne
   GitHub-Bezug werden als Issues angelegt und erhalten eine Verweiszeile
   `GitHub: #<n>`; auf GitHub geschlossene Issues schließen beim nächsten
   Sync den lokalen Block (`[x]` + Nachweiszeile).
2. **Draft/Ready-Freigabe (Nutzer-Addendum):** neue Tickets sind
   standardmäßig Entwürfe (`Status: draft`, auf GitHub ohne Ready-Label) und
   werden vom Läufer übersprungen; erst die Freigabe (Label `ready`) nimmt
   sie in die Arbeitsauswahl auf. Rohdrafts lassen sich gefahrlos anlegen und
   synchronisieren.
3. **Drei Zustände:** Offen (ready), In Progress (GitHub-Label `in-progress`,
   lokal `Status: in-progress`), Closed (`[x]`); Draft als vierter
   Vormerkzustand vor der Freigabe.
4. **Nur zugewiesene Tickets:** mit `GITHUB_ISSUES_ASSIGNEE` führt der lokale
   Hub ausschließlich dem Nutzer zugewiesene Issues; neue Issues werden
   diesem Nutzer zugewiesen.
5. **PR schließt das Ticket:** der Runner-Pfad (`complete_package`) hängt bei
   Issue-Bezug automatisch `Closes #<n>` an den Merge-Request; GitHub schließt
   das Issue beim Merge, der nächste Sync schließt den lokalen Block.
6. **Kategorie Bug/Feature:** im verbundenen Ticket-Formular wählbar; `bug`
   wird lokal als `Art: Bug` gespiegelt.
7. **Lokal ohne GitHub unverändert:** ohne `GITHUB_ISSUES_ENABLED="1"`
   existiert kein einziges Issue-Verhalten, keine Netzaufrufe, keine
   Formatänderungen.

Die Oberfläche (Nova) bleibt von der Backend-API getrennt: der komplette
REST-Zugriff liegt im neuen Backbone-Modul `bin/vibe_issues.py` (über die
bestehenden `vibe_github`-Helpers); Web-API und CLI rufen ausschließlich
Dienstfunktionen auf. Ein künftiger Wechsel des Server-Providers bedeutet den
Austausch genau dieses Moduls.

## 2. Umsetzung

| Fläche | Datei(en) | Inhalt |
|---|---|---|
| Backbone | `bin/vibe_issues.py` (neu, 559 Zeilen) | `list_issues` (state=all, ohne PRs, Assignee-Filter), `get_issue`, `create_issue`, `update_issue` (PATCH, Labels), `sync_issues` (Pull+Push+Close mit Statistik created/updated/closed/pushed), `set_issue_state` (draft/ready/in-progress/open), `add_ticket_connected` (Issue zuerst, dann lokaler Block). TICKETS.md ausschließlich über `vibe_storage` atomar mit Digest-Erkennung; Konflikt → Fehlermeldung statt stiller Überschreibung. REST nur über `vibe_github` (token_for_rest, check_api, GitHubError, Maskierung). Beschreibungs-Folgezeilen werden über `_neutralize_description_line` entschärft (Review-Runde 1): Issue-Texte können nie als `Status:`-/`GitHub:`-/`BLOCKIERT:`-/`Commit:`-Steuerzeilen wirken (Zeileninjektion). |
| Installer | `scripts/setup-vibe.py` | `PROGRAM_FILES` um `vibe_issues.py` ergänzt (Review-Runde 1, [High]): ohne den Eintrag bräche jede installierte Instanz mit `ModuleNotFoundError: No module named 'vibe_issues'` ab; die gespiegelten Testfixtures wurden durch den Test-Agenten analog aktualisiert. |
| Konfiguration | `bin/vibe_github.py` | `read_config`/`status` führen zusätzlich `issues_enabled`, `issues_in_progress_label`, `issues_ready_label`, `issues_assignee`. |
| PR-Abschluss | `bin/vibe_github.py` | `_package_issue_number` (Bezug über ID `GH-<n>` oder `GitHub: #n`-Zeile); `complete_package` hängt `Closes #<n>` an den PR-Body, ohne Bezug bleibt der Body unverändert. |
| Parser | `bin/vibe` | `Status:` als bekanntes Label; Ticket-Zeilen führen zusätzlich `status` (`in-progress`/`draft`) und `github` (Issuenummer); Präzedenz: erledigt > BLOCKIERT > WARTET AUF MERGE > In Progress > Draft > offen. Bestandsfelder unverändert; FEEDBACK.md-Parsing bleibt funktionsfähig. |
| Läufer-Filter | `bin/vibe_packages.py` | `is_draft(block)` (exakt zeilenankerierte `Status: draft`-Zeile); `select_package` überspringt Drafts in allen drei Auswahlwegen (PACKAGE_ORDER, TICKETS-Priorität, Standardordnung); `prefer` (Reattach) gewinnt bewusst, wie bei BLOCKIERT. |
| Web-API | `bin/vibe-web.py` | `/api/github`: `settings` akzeptiert `issues_enabled/issues_in_progress/issues_ready/issues_assignee`; neue Aktionen `issues.sync` (Statistik) und `issues.state` (`id`,`state`); `/api/ticket add` legt im verbundenen Projekt zuerst das Issue an (Kategorie `bug`/`feature`, `draft`, Standard: Entwurf), ID `GH-<n>`, bei REST-Fehler kein halbfertiger lokaler Eintrag. |
| CLI | `bin/vibe` | `vibe github <projekt> issues-sync`; `vibe github <projekt> issues-state <id> draft|ready|in-progress|open`; `status` nennt den Issues-Sync-Zustand. |
| Oberfläche | `bin/web/nova-project.js`, `bin/web/i18n.js` | Board: gelbe Pille „In Progress“, graue Pille „Entwurf“; Sync-Button `data-nv-action="issues-sync"` (nur bei aktivem Sync); Zustandsaktionen `data-nv-action="issues-state"` je Ticketkarte (draft/ready/in-progress, nur bei Issue-Bezug); Ticket-Formular: Draft-Checkbox `data-nv-field="draft"` (Vorgabe gesetzt) + Kategorie-Select `data-nv-field="category"` (Bug/Feature); GitHub-Karte: Schalter `data-nv-field="github-issues-enabled"` + Felder für In-Progress-/Ready-Label und Assignee (gespeichert über `settings`). |

## 3. Getroffene Entscheidungen

1. **Opt-in binär:** nur exakt `GITHUB_ISSUES_ENABLED="1"` aktiviert; alles
   andere bleibt aus (gleiches Muster wie `GITHUB_AUTO_MERGE`).
2. **Sync per bewusstem Button statt Auto-Refresh:** Netz- und Token-Nutzung
   nur auf ausdrückliche Nutzerhandlung; kein Überraschungscall beim Render.
3. **Draft als Standard:** neue Tickets (Formular, Sync-Pull ohne Ready-Label)
   sind Entwürfe; Freigabe ist eine bewusste Handlung (Label `ready`).
   Migration: vorher als offen synchronisierte Issues ohne Ready-Label werden
   beim nächsten Sync zu Drafts.
4. **Zustandstreue in beide Richtungen:** Pull aktualisiert Zustand und Titel
   vom Remote-Stand; die Beschreibung nur bei Neuanlage (lokale
   Bearbeitungen bleiben erhalten). Push legt Issues mit dem lokalen Zustand
   an (ohne Statuszeile → mit Ready-Label; `Status: draft` → ohne).
5. **Lokale IDs bleiben stabil:** beim Push wird keine Kennung umbenannt;
   der GitHub-Bezug lebt in der Verweiszeile `GitHub: #<n>` (Runner- und
   Worktree-Registrierungen brechen nicht). Neue verbundene Tickets erhalten
   `GH-<n>`.
6. **Sync führt alle Issues** (GitHub als Quelle), nicht nur `GITHUB_LABEL`;
   die bestehenden Aktionen `issues`/`issues-import` bleiben unverändert
   (Legacy für den Nicht-Sync-Betrieb).
7. **Keine GitHub-Priority-Anbindung:** GitHub Issues haben kein
   Prioritätsfeld; lokale Priorisierung (`PACKAGE_ORDER`, `/api/priority`)
   bleibt alleinige Quelle der Arbeitsreihenfolge.
8. **Reattach unverändert übernommen:** Session-/Worktree-Wiederverbindung
   (AP4) gilt weiterhin für offene Tickets; kein neuer Code.
9. **Grenzen bewusst gesetzt:** der Runner setzt kein In-Progress
   automatisch (Status nur über State-Aktionen/API/CLI); die klassische UI
   bleibt unberührt; nur bug/feature als Kategorien.

## 4. Geänderte Schnittstellen

- `.vibe/project.env` (neu): `GITHUB_ISSUES_ENABLED`, `GITHUB_ISSUES_IN_PROGRESS`
  (Default `in-progress`), `GITHUB_ISSUES_READY` (Default `ready`),
  `GITHUB_ISSUES_ASSIGNEE` (leer = alle).
- `vibe_github.read_config()/status()`: neue Felder `issues_enabled`,
  `issues_in_progress_label`, `issues_ready_label`, `issues_assignee`.
- `vibe_issues` (neues Backbone): `list_issues`, `get_issue`, `create_issue`,
  `update_issue`, `sync_issues`, `set_issue_state`, `add_ticket_connected`.
- Web-API `/api/github`: `settings` (neue Schlüssel `issues_enabled`,
  `issues_in_progress`, `issues_ready`, `issues_assignee`), Aktionen
  `issues.sync`, `issues.state`; `/api/ticket add`: neue Felder `category`
  (`bug`/`feature`), `draft` (Standard: gesetzt, nur mit Sync wirksam).
- Ticket-Zeilen (`ticket_items`): zusätzliche Felder `status`, `github`.
- `TICKETS.md`-Blockformat (additiv): `  Status: draft`,
  `  Status: in-progress`, `  GitHub: #<n>`.
- CLI: `vibe github <projekt> issues-sync|issues-state <id>
  draft|ready|in-progress|open`; `vibe github <projekt> status` zeigt den
  Issues-Sync-Zustand.
- `scripts/setup-vibe.py`: `PROGRAM_FILES` enthält `bin/vibe_issues.py`
  (Installer-Vollständigkeit; Review-Runde 1).
- `vibe_packages`: neue Helper-Funktion `is_draft`; `select_package`
  überspringt Drafts (außer bei `prefer`).

## 5. Nachweise

Unabhängiger Test-Agent (Rotphase vor Implementierung, Grünphase danach;
Bericht `docs/reviews/AP3-Korbat-test-agent-report.md` mit allen Fällen als
Vorbedingung/Aktion/Erwartung):

- `python3 -m unittest tests.unit.test_github_issues -v`
  → Rot: Ran 29, FAILED (failures=24, errors=6); Grün: **Ran 32, OK**
  (29 Grundfälle + 3 Fälle aus Review-Runde 1).
- `python3 -m unittest tests.unit.test_github_issues -v`
  → Rot: Ran 23, FAILED (failures=21); Grün: **Ran 25, OK**
  (23 Grundfälle + 2 Fälle aus Review-Runde 1).
- Gesamt **57/57 grün**, bestätigt vom Test-Agenten nach Integritätsprüfung
  (keine entfernten/abgeschwächten Assertions, kein Sonderweg im
  Produktionscode). Bewusst vorab grüne Fälle dienen der Regressionssicherung.
- Kein echtes GitHub: REST ausschließlich gegen Loopback-Fakes
  (127.0.0.1, Fake-Token); Git nur in temporären Verzeichnissen; isolierte
  Umgebung nach Bestandsmuster (ISOLATED_ENV wie test_ap4_korbat_github).

Regression der berührten Bestandsmodule (`env -u GITHUB_AUTO_MERGE`):
Ran 267, failures=9, errors=1 — alle 10 Fehlfälle Fall für Fall als
**vorbestehend** klassifiziert, keine neuen Fehler:

| Fehlfamilie | Fälle | Baseline-Beleg |
|---|---|---|
| test_project_management (TemplateRulesTest/InitTest) | 7 | AP5 §5 „F22-Altschuld“: Test-Agenten-Vorlage/TESTER-Token existieren bewusst nicht (`git ls-tree HEAD templates/common/.opencode/` = 0 Treffer) |
| test_ap06_github.CliPushTest | 1 | AP4-Nachweis (TICKETS.md Z. 150): am Ausgangscommit 212d97d als vorbestehend verifiziert |
| test_ap12_github_readiness (Hygiene/Untracked) | 2 | AP5 §5 dokumentierte Drift (`docs/features/AP21.md`-Altbestand; `.opencode/agents/test-agent.md` fehlt) — Dateien nicht im AP3-Diff |

Statische Prüfungen und Schnellprüfung (tatsächlich ausgeführt):

- `python3 scripts/check-syntax.py` → OK (220 Python-, 8 Bash-, 3 JSON-Dateien), Exit 0
- `python3 scripts/check-no-secrets.py` → OK, Exit 0
- `python3 scripts/check-import-manifest.py` → OK (68 Dateien), Exit 0
  (Manifest für die 8 AP3-Produktionsdateien aktualisiert, inkl. neuem
  `bin/vibe_issues.py` und `scripts/setup-vibe.py`; `aenderungen`-Eintrag
  AP3-Korbat ergänzt)
- `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh quick` → Exit 0

Unabhängige Reviews (Berichte unverändert gesichert):

- Runde 1 (`docs/reviews/AP3-Korbat-review-1.md`): `CHANGES REQUIRED` —
  1×High (Installer-Liste), 3×Medium (Zeileninjektion, In-Progress-Pille,
  GH-ID-Gate), 1×Minor (Manifest-Änderungseintrag). Alle fünf Behhebungen
  umgesetzt; die Befundfälle wurden vorher vom Test-Agenten unabhängig
  abgeleitet und rot belegt (Bericht §10).
- Runde 2 (`docs/reviews/AP3-Korbat-review-2.md`): **`Verdict: PASS`** —
  0 offene Befunde, inklusive Audit der testseitigen Änderungen
  (`_scan_blocks`-Aufrufkorrektur, drei gespiegelte `PROGRAM_FILES`-Fixtures)
  ohne jede Abschwächung und Bestätigung der B17-Baseline-Zuordnung der
  verbleibenden Installer-Rotfälle (`test_setup_vibe`: 6 Failures/4 Errors;
  `test_install_lifecycle`: 7/28; kausaler Wächter
  `test_every_module_imported_by_the_launcher_is_installed` und
  `test_b17_isolation` 12/12 grün).

`scripts/verify.sh full` ist in dieser Arbeitskopie nicht als vollständiger
Nachweis ausführbar: Die transportierte, bewusst schreibgeschützte
`.vibe/project.env` (Autorität: produktive Instanz) definiert keinen
`VERIFY_TESTS`-Schlüssel, den der Vollmodus zwingend verlangt (Exit 6,
Testnachweis-Fehler) — dieselbe Umgebungsbedingung, die AP5 dokumentiert hat.
Als äquivalenter Vollnachweis läuft die komplette Unit-Suite einmal über
`env -u GITHUB_AUTO_MERGE python3 scripts/run-tests-parallel.py --dir
tests/unit --jobs 4`; das Ergebnis wird hier und im TICKETS.md-Nachweis
festgehalten.

Volllauf-Ergebnis (2026-11-22, einmal vor Abnahme):
**2302 Tests, 95/131 Module bestanden, 36 Module rot.** Abgleich gegen die
dokumentierte Baseline (AP5 §5, Option A): **35 Module vorbestehend** —
33 deckungsgleich mit der AP5-Klassifizierung (Umgebungsfamilie
„vibe-web ist nicht erreichbar“/bwrap/tmux, Drift, F22-Altschuld), zwei
am Ausgangsstand 6449438 per `git archive`-Export mit identischer
project.env und identischer Fehlersignatur reproduziert
(`test_ap8_github_checkout.LocalAdoptionTest`,
`test_verify_script.RepositoryVerifyTest`). Genau EIN Fall war eine
AP3-Vertragsänderung: das Nova-Board führt die neuen Spalten
`['open', 'progress', 'draft', 'waiting', 'blocked', 'proof', 'done']`;
der Bestandstest
`test_nova_board_orders_the_waiting_column_between_open_and_blocked`
wurde darauf vom unabhängigen Test-Agenten fortgeschrieben
(`tests/unit/test_ap5_korbat_waiting_state.py:543 ff.`, Absicht erhalten:
waiting nach den Arbeitszuständen, vor blocked; keine Abschwächung,
Bericht §12). Nach der Fortschreibung:
`env -u GITHUB_AUTO_MERGE python3 -m unittest
tests.unit.test_ap5_korbat_waiting_state -v` → **Ran 23, OK**;
Kombinationslauf mit ap8/verify_script → Ran 90, FAILED (failures=2) mit
ausschließlich den beiden am Ausgangsstand reproduzierten Vorlast-Fällen.
Kein Modul, das am Ausgangsstand grün war, bleibt ohne fortgeschriebenen
Vertrag rot.

Grenzen des Nachweises: Playwright ist in dieser Umgebung nicht verfügbar —
die Nova-Oberfläche ist per Strukturassertionen (Quelltext-Hooks, i18n-Schlüssel,
Pillen/Spalten) abgesichert, echte Browsertests stehen aus; echte
GitHub-Rest-Aufrufe wurden bewusst nicht durchgeführt (Token-Nutzung nur gegen
Loopback-Fakes).

## 6. Vom Nutzer selbst vorzunehmende Schritte (nicht durch Agenten umgesetzt)

1. In `.vibe/project.env` des Projekts `GITHUB_ISSUES_ENABLED=1` setzen
   (Token wie bisher in der Karte „Git & GitHub“ hinterlegen; der Token
   benötigt Read & Write für Issues).
2. Auf GitHub die Labels `ready` und `in-progress` anlegen oder eigene Namen
   über `GITHUB_ISSUES_READY`/`GITHUB_ISSUES_IN_PROGRESS` konfigurieren.
3. Optional `GITHUB_ISSUES_ASSIGNEE=<login>` setzen, damit der Hub nur mit
   dem eigenen Tickets arbeitet.
4. Bestehende, früher als offen synchronisierte Issues einmalig mit `ready`
   versehen (Migration, siehe §3.3) — danach erst Läufe starten.
5. `AGENTS.md`-Anpassungen sind für AP3 nicht erforderlich (keine Regeländerung
   für Agentenprozesse); die Ticket- und Nachweiskonventionen bleiben
   unverändert.
6. Für einen vollständigen `verify.sh full`-Nachweis in künftigen Läufen
   `VERIFY_TESTS` in der produktiven `.vibe/project.env` setzen (z. B.
   `VERIFY_TESTS="python3 -m unittest discover -s tests/unit -v"`); die
   transportierte Arbeitskopie ist bewusst schreibgeschützt und wird nie
   zurückgeschrieben.

## 7. Offene Punkte / bekannte Baseline-Defekte (nicht AP3)

- Die 10 klassifizierten Vorlast-Fehler (F22-Altschuld-Familie
  Test-Agenten-Vorlage/TESTER-Token, CliPushTest, Hygiene-Drift) bleiben
  bestehen und sind vor AP3 belegt (§5).
- Die verbleibenden Installer-Rotfälle (`test_setup_vibe`: 6 Failures/
  4 Errors; `test_install_lifecycle`: 7/28) sind die dokumentierte
  B17-Baseline (`_toolchain`-Pfadversatz, `register_projects`-Signatur);
  der kausale AP3-Wächter
  `test_every_module_imported_by_the_launcher_is_installed` und
  `test_b17_isolation` (12/12) sind grün (Review-Runde 2 bestätigt).
- Browserabnahme der neuen Nova-Elemente (Playwright) und echte
   GitHub-Kompatibilität (REST-Schema in freier Wildbahn) sind nicht
   automatisch geprüft; die REST-Aufrufe folgen der dokumentierten
   GitHub-v3-Syntax und sind über Loopback-Fakes verifiziert.
- Der Runner setzt kein In-Progress-Label automatisch beim Paketstart
   (bewusste Grenze, §3.9).
- Issues-Paginierung über 100 Einträge hinaus erfolgt nicht
   (`per_page=100`, kein Link-Header-Folgeabruf) — dokumentierte Grenze.
