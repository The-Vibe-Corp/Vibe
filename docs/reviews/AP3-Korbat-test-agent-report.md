# AP3-Korbat — Bericht des unabhängigen Test-Agenten

Stand: 2026-11-22
Arbeitspaket: **AP3-Korbat — Add GitHub Issues Support**
Branch: `feature/korbat/ap3-korbat`
Ausgangscommit der Rotphase: `6449438`
Rolle: unabhängiger Test-Agent. Es wurden ausschließlich neue Testdateien
angelegt und ausgeführt; kein Produktionscode, keine Build-/Prüfskripte, keine
bestehenden Tests und kein Commit wurden verändert.

Quellen der Ableitung (bewusst **nicht** aus einem Implementierungsdiff — es
existiert noch keiner):

- `TICKETS.md`, Eintrag AP3-Korbat (Zeilen 119–123)
- `SPEC.md` („Arbeitspakete und Feedback“, „Sicherheit und Datenintegrität“,
  „Qualität und Abnahme“, „Git & work-package closing (runner-owned)“)
- `AGENTS.md` (unabhängiger Test-Agent, lokale Instanz unverändert, keine
  echten Modell-/Netzaufrufe)
- verbindliche Design-Entscheidungen des Koordinators 1–14

## 1. Angelegte Testdateien

Neu angelegt (nur diese Dateien, keine Bestandsänderung):

- `tests/unit/test_ap3_korbat_issues_backend.py` — 32 Testfälle
  (Konfiguration, Backbone-Sync, Parser, Entwurfsauswahl, Runner-Abschluss,
  Review-Runde-1-Fälle für Zeileninjektion und Legacy-GH-Bezug)
- `tests/unit/test_ap3_korbat_surfaces.py` — 25 Testfälle
  (Web-API, CLI, Nova-Struktur; inkl. Review-Runde-1-Fälle für Pillenfarbe
  und GH-ID ohne Verweiszeile)

Gesamt: **57 Testfälle** in zwei Modulen (52 aus der ursprünglichen Abnahme,
5 zusätzlich aus Review-Runde 1).

Kein echtes Netz, kein echtes GitHub, keine Modellaufrufe:

- REST ausschließlich gegen `ThreadingHTTPServer` auf `127.0.0.1` mit
  dynamischem Port und `close()` per `addCleanup`/`tearDownClass`.
- Git nur in temporären Verzeichnissen mit fester Test-Identität gegen lokale
  Bare-Repositories (`file://`).
- Isolation über `VIBE`/`HOME`/`VIBE_STATE`/`GITHUB_TOKEN`/`GH_TOKEN`/
  Proxy-Variablen; Fake-Token `ap3-korbat-fake-token-4711`, keine produktiven
  Pfade.
- Der Webserver läuft über die bestehende `DashboardFixture` auf einem freien
  Loopback-Port mit isoliertem `HOME` und `VIBE`.

## 2. Testfälle je Design-Entscheidung

Jede Testmethode trägt im Quelltext einen Docstring mit Vorbedingung, Aktion,
erwartetem Ergebnis und Fehlerfall.

### 2.1 Opt-in, Konfiguration und Status (Design 1/2)

Modul `test_ap3_korbat_issues_backend.py`, Klasse `IssuesConfigTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_missing_issues_keys_default_off_and_in_progress` | `project.env` ohne Issues-Schlüssel | `vibe_github.read_config` | `issues_enabled is False`, Label `in-progress`, Ready-Label `ready`, Assignee leer; Fehler: fehlende Schlüssel/Wahrwert |
| `test_only_exact_one_enables_the_issue_sync` | Werte `""`, `true`, `on`, `yes`, `1` | `read_config` je Wert | nur exakt `"1"` aktiv; Fehler: `true`/`on` aktivieren oder `1` nicht |
| `test_ready_label_default_and_override` | `GITHUB_ISSUES_READY` fehlt/gesetzt | `read_config` | Default `ready`, sonst eigener Wert; Fehler: Wert ignoriert |
| `test_status_exposes_the_issues_settings` | aktiver Sync, Label `triaged`, Ready `freigegeben`, Assignee `alice` | `vibe_github.status(project, remote=False)` | Status trägt alle Werte; Fehler: verschwiegen oder als String |

### 2.2 Backbone-Modul, Pull, Push und Entwurfszustand (Design 3/4/5/6/13/16/18/20)

Modul `test_ap3_korbat_issues_backend.py`, Klasse `IssuesSyncTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_backbone_module_uses_vibe_github_for_rest` | `bin/vibe_issues.py` | Modul laden, Quelltext prüfen | `sync_issues` aufrufbar; REST über `vibe_github`, kein eigenes `urllib.request`/`http.client`; Fehler: Modul/Funktion fehlt oder REST dupliziert |
| `test_sync_ignores_the_legacy_github_label_filter` | `GITHUB_LABEL="vibe"`, Remote-Issues ohne dieses Label | `sync_issues` | alle Issues werden geführt (GH-101/GH-102); Fehler: Legacy-Labelfilter greift im Sync |
| `test_pull_creates_blocks_and_skips_pull_requests` | leere `TICKETS.md`; Remote: offen, in-progress, geschlossen, PR | `sync_issues` | `GH-101` mit Beschreibung, `GitHub: #101`, `Art: Bug`; `GH-102` mit `Status: in-progress`; PR nicht als Ticket; `state=all`; `created == 2` |
| `test_pull_does_not_duplicate_and_updates_open_blocks` | lokale Blöcke `GH-101` (alter Titel), `AP7` mit `GitHub: #102` | `sync_issues` zweimal | genau ein GH-101/Verweis; Titel vom Remote aktualisiert; AP7-ID bleibt, kein GH-102-Duplikat, `Status: in-progress`; zweiter Lauf ohne neue Blöcke |
| `test_closed_issue_marks_the_local_block_done` | lokaler offener Block `GH-103`; Remote geschlossen | `sync_issues` | Block `[x]`; Nachweiszeile mit `#103` und „geschlossen“; `closed == 1` |
| `test_pull_state_is_authoritative_and_descriptions_stay_local` | lokale Blöcke mit veralteten Zuständen/Beschreibungen; Remote draft/in-progress/ready/closed plus neues GH-106 | `sync_issues` | Zustände autoritativ (`draft`/`in-progress`/keine Zeile/`[x]`), Titel aktualisiert, lokale Beschreibungen erhalten; GH-106 mit Remote-Body neu |
| `test_previously_open_issue_without_ready_label_becomes_draft` | offener Block ohne Statuszeile; Remote ohne Ready-Label | `sync_issues` | Block erhält `Status: draft` (bewusste Migration) |
| `test_push_creates_issues_for_open_local_packages_only` | AP1 offen, AP2 offen + `Art: Bug`, AP3 erledigt, Feedback | `sync_issues` | zwei POSTs (AP1/AP2), AP2-Label `bug`; AP3/Feedback nicht gepusht; lokale IDs bleiben, `GitHub: #n` ergänzt; `pushed == 2` |
| `test_push_preserves_draft_and_ready_state` | AP1 ohne Status, AP2 mit `Status: draft` | `sync_issues` | AP1-Issue mit Ready-Label, AP2-Issue ohne; lokale IDs/Status bleiben |
| `test_assignee_filter_limits_pull_and_assigns_new_issues` | `GITHUB_ISSUES_ASSIGNEE="alice"`, Issue 101 Alice, 102 Bob | `sync_issues` | nur GH-101 lokal; neues Issue für AP1 mit `assignees=["alice"]` |
| `test_assignee_and_draft_compose_for_work_selection` | Alice zugewiesen: GH-102 ready, GH-103 draft; Bob: GH-101/GH-104; `PACKAGE_ORDER="GH-103 GH-102"` | `sync_issues`, dann `select_package` | nur zugewiesene Issues lokal; GH-102 ohne Status, GH-103 `Status: draft`; GH-102 wird trotz Ordnung gewählt |
| `test_conflicting_ticket_change_is_reported_not_overwritten` | Schreibkonflikt beim ersten atomaren Schreiben | `sync_issues` mit `ConcurrentChangeError` | Sync meldet Konflikt (Ausnahme/Ergebnistext) und überschreibt nicht still; Fehler: Konflikt verschluckt |

### 2.3 Parser und Zustands-Präzedenz (Design 5)

Modul `test_ap3_korbat_issues_backend.py`, Klasse `TicketParserTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_status_and_github_reference_are_exposed_additively` | Block mit `Status: in-progress` und `GitHub: #103` | `ticket_items` | `status == "in-progress"`, `github == 103`, `completed False`, Titel/Beschreibung sauber; Fehler: Felder fehlen oder Beschreibung schluckt Metazeilen |
| `test_legacy_open_block_keeps_its_fields` | klassischer offener Block | `ticket_items` | Zustand `offen`, `status` leer/None, `github None`; Fehler: Bestandsfelder ändern sich |
| `test_state_precedence_keeps_runner_states_above_in_progress` | `Status: in-progress` plus BLOCKIERT/WARTET/erledigt/offen | `ticket_items` | erledigt > BLOCKIERT > WARTET AUF MERGE > In-Progress > offen; reiner In-Progress-Block nicht `offen`; Fehler: Schranke maskiert |
| `test_draft_status_is_exposed_with_precedence` | `Status: draft` allein und mit In-Progress/BLOCKIERT/WARTET/erledigt | `ticket_items` | `status == draft`, Zustand nicht `offen`; Präzedenz erledigt > BLOCKIERT > WARTET > In-Progress > Draft |
| `test_feedback_parsing_remains_functional` | normales Bug-Feedback | `feedback_items` | `kind == bug`, Zustand offen; Fehler: additive Parseränderung bricht FEEDBACK.md |

### 2.4 Runner-Abschluss „Closes #123“ (Design 8)

Modul `test_ap3_korbat_issues_backend.py`, Klasse
`CompletePackageClosesIssueTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_issue_id_in_the_block_appends_closes_to_the_pr_body` | Ticketblock `GH-77`, Featurebranch, Fake-REST | `vibe_github.complete_package(..., package_id="GH-77")` | PR-Body enthält `Closes #77`; Fehler: PR ohne Close-Verweis |
| `test_github_reference_line_appends_closes_to_the_pr_body` | Paket `AP9` mit `GitHub: #551` | `complete_package(..., "AP9")` | PR-Body enthält `Closes #551` |
| `test_package_without_issue_reference_keeps_the_pr_body` | Paket `AP10` ohne Bezug | `complete_package(..., "AP10")` | kein `Closes` im Body |

### 2.5 Web-API-Einstellungen (Design 1/2/11)

Modul `test_ap3_korbat_surfaces.py`, Klasse `IssuesSettingsApiTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_settings_persist_issues_options_and_status` | verbundenes Projekt | `POST /api/github {action:"settings", issues_enabled:true, issues_in_progress:"triaged", issues_ready:"freigegeben", issues_assignee:"alice"}` | `GITHUB_ISSUES_ENABLED="1"`, `GITHUB_ISSUES_IN_PROGRESS="triaged"`, `GITHUB_ISSUES_READY="freigegeben"`, `GITHUB_ISSUES_ASSIGNEE="alice"`; Status liefert Werte |
| `test_settings_can_turn_the_issue_sync_off_again` | Sync aktiv | `settings {issues_enabled:false}` | `GITHUB_ISSUES_ENABLED=""`, Status aus |

### 2.6 Web-API-Sync und Zustand (Design 4/6/7/10)

Modul `test_ap3_korbat_surfaces.py`, Klasse `IssuesSyncApiTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_sync_without_opt_in_is_refused_without_network` | Issues-Opt-in fehlt | `POST /api/github {action:"issues.sync"}` | `ok:false` mit verständlicher Meldung; Fake erhält **null** Aufrufe; TICKETS.md unverändert |
| `test_sync_returns_statistics_and_updates_tickets` | Sync aktiv; Remote 101, lokal AP1 | `issues.sync` | 200/ok; Statistik `created/updated/closed/pushed`; GH-101 gepullt, AP1 erhält GitHub-Verweis |
| `test_state_action_sets_and_removes_the_in_progress_label` | Block `GH-101` | `issues.state` mit `in-progress`, dann `open` | genau ein PATCH je Aktion; Label gesetzt/entfernt; lokale `Status:`-Zeile erscheint/verschwindet |
| `test_state_action_supports_draft_and_ready` | Remote 101 mit `ready`+`in-progress`, lokal `Status: in-progress` | `issues.state` mit `draft`, `ready`, `in-progress` | draft entfernt beide Labels, ready setzt Ready/entfernt In-Progress, in-progress setzt In-Progress/lässt Ready; lokale Zeile folgt |

### 2.7 Ticket-Anlage über die Web-API (Design 9)

Modul `test_ap3_korbat_surfaces.py`, Klasse `TicketAddApiTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_bug_category_creates_issue_and_github_block` | Sync aktiv | `POST /api/ticket {action:"add", category:"bug"}` | Issue mit Label `bug`; lokaler Block `GH-<n>`, `GitHub: #<n>`, `Art: Bug` |
| `test_feature_category_uses_the_feature_label` | Sync aktiv | Kategorie `feature` | Issue mit Label `feature`; Block ohne `Art: Bug` |
| `test_ticket_add_defaults_to_draft_in_connected_projects` | Sync aktiv, kein `draft` im Request | `add` mit `bug` | Issue ohne Ready-Label; lokaler Block `Status: draft` |
| `test_ticket_add_with_draft_false_creates_a_ready_issue` | Sync aktiv | `add` mit `draft:false` | Issue mit Ready-Label; Block ohne Statuszeile |
| `test_failed_issue_creation_leaves_no_local_entry` | Fake lehnt Issue-Anlage ab | `add` mit `bug` | `ok:false`; TICKETS.md unverändert (kein GH-/AP-Block) |
| `test_without_issue_sync_the_local_auto_id_is_kept` | Issues-Opt-in aus | `add` mit `draft:true` | lokaler `AP1`-Block ohne Statuszeile; kein REST-POST |

### 2.8 CLI (Design 10)

Modul `test_ap3_korbat_surfaces.py`, Klasse `IssuesCliTest` (echter
`bin/vibe`-Prozess mit isolierter Umgebung):

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_issues_sync_without_opt_in_makes_no_request` | Opt-in aus | `vibe github proj issues-sync` | Exit ≠ 0, klare Meldung, kein REST-Aufruf, TICKETS.md unverändert |
| `test_issues_sync_pulls_a_remote_issue` | Opt-in an, Remote 101 | `vibe github proj issues-sync` | Exit 0; GH-101 in TICKETS.md |
| `test_issues_state_sets_and_removes_the_local_status_line` | Block GH-101 | `issues-state GH-101 in-progress` / `... open` | Exit 0; Statuszeile erscheint/verschwindet; ≥ 2 PATCHs |
| `test_issues_state_supports_draft_and_ready` | Remote 101 mit `ready`+`in-progress` | `issues-state GH-101 draft\|ready\|in-progress` | Exit 0 je Aktion; Statuszeile draft → keine → in-progress; PATCH-Labels wie Design 19 |

### 2.9 Nova-Oberfläche (Design 11, ohne Browser)

Modul `test_ap3_korbat_surfaces.py`, Klasse `NovaIssuesSurfaceTest`
(Strukturassertionen gegen `bin/web/nova-project.js`; Playwright ist in dieser
Umgebung nicht verfügbar, wie AP2/AP4):

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_state_helpers_know_in_progress` | `nvpStateColumn`/`nvpStateLabel` | Quelltextabschnitte | In-Progress wird auf eigene Spalte abgebildet und beschriftet; Fehler: Rückfall auf „offen“ |
| `test_board_and_tiles_include_the_progress_column` | Board/Kacheln | Abschnitte prüfen | Progress-Spalte im Board, In-Progress-Zählung in den Kacheln |
| `test_github_card_has_sync_button_and_issues_fields` | `nvpGithubSection` | Aktionen/Felder | `issues-sync`, `github-issues-enabled`, In-Progress-/Ready-Label, Assignee, Payload `issues_enabled`/`issues_in_progress`/`issues_ready`/`issues_assignee` |
| `test_nova_board_shows_draft_state_and_gray_pill` | Zustandshelfer/Board | Abschnitte prüfen | eigene Draft-Spalte, Beschriftung „Entwurf“, graue Pillen-Klasse (`nv-*draft`/`nv-*muted`) |
| `test_ticket_cards_have_issue_state_actions` | `nvpBoardColumn` | Kartenaktionen | `issues-state` mit draft/ready/in-progress; Sync-Gating im File |
| `test_ticket_form_has_draft_checkbox` | `nvpOpenTicketForm` | Formular/Payload | Feld `draft` mit Vorgabe gesetzt; `draft` im Request-Body |
| `test_ticket_form_offers_bug_and_feature_categories` | Ticketformular/Arbeitsbereich | Kategorieauswahl | Feld `category` mit Bug/Feature; Arbeitsbereich kennt `issues_enabled` |

### 2.10 Draft/Ready-Entwurfszustand (Nachtrag Design 15–21)

Modul `test_ap3_korbat_issues_backend.py`, Klasse `DraftSelectionTest`
(`bin/vibe_packages.py`):

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_is_draft_requires_the_exact_status_line` | `Status: draft`, nur „draft“ im Beschreibungstext, kein Status | `is_draft` | nur die exakte Statuszeile ist Draft; Freitext nicht |
| `test_package_order_skips_a_draft` | `PACKAGE_ORDER="T1 T2"`, T1 Draft | `select_package` | T2 wird gewählt |
| `test_ticket_priority_order_skips_a_draft` | T1 P0-Draft, T2 offen | `select_package` | T2 wird gewählt |
| `test_default_and_feedback_order_skip_a_draft` | T1 Draft, F1 Feedback | `select_package` | F1 wird gewählt; ohne F1 `None` |
| `test_prefer_reattaches_a_draft_package` | T1 Draft, T2 offen | `select_package(prefer="T1")` | T1 wird bewusst erneut gewählt |

Die drei Auswahlwege (PACKAGE_ORDER, TICKETS-Priorität, Standard/FEEDBACK)
sind damit einzeln abgedeckt; `prefer` gewinnt wie bei BLOCKIERT.
Die übrigen Draft/Ready-Fälle stehen in den Tabellen 2.1–2.9 und decken
Konfiguration, Parser-Präzedenz, Pull-Autorität, Push-Zustandstreue,
State-Aktion, Ticket-Anlage (Draft-Standard/`draft:false`), CLI und Nova ab.
Der Assignee-Verbund ist in `test_assignee_and_draft_compose_for_work_selection`
(2.2) abgesichert.

## 3. Rotphase auf dem unveränderten Stand `6449438`

Beide Module wurden vor jeder Implementierung tatsächlich ausgeführt. Die
Rotphase ist reproduzierbar; das Backbone-Modul `bin/vibe_issues.py` und die
neuen Parser-/API-/UI-Funktionen fehlen vollständig.

### 3.1 Backend

```
python3 -m unittest tests.unit.test_ap3_korbat_issues_backend -v
```

Ergebnis: **Exit 1**, `Ran 29 tests`, `FAILED (failures=24, errors=6)`.

- 24 Testmethoden scheitern (u. a. fehlende Konfigurationsschlüssel,
  fehlendes `bin/vibe_issues.py`, fehlende `status`/`github`-Felder,
  fehlendes `Closes #n`, fehlende Draft-Unterstützung).
- 6 `ERROR`-Einträge: fünf Subtest-Werte von
  `test_only_exact_one_enables_the_issue_sync` (Attribut `issues_enabled`
  fehlt) und `test_is_draft_requires_the_exact_status_line`
  (`vibe_packages.is_draft` fehlt).
- Bewusst grün (Regressionsschutz, kein neues Verhalten):
  `test_package_without_issue_reference_keeps_the_pr_body`,
  `test_legacy_open_block_keeps_its_fields`,
  `test_feedback_parsing_remains_functional`,
  `test_prefer_reattaches_a_draft_package` (Reattach funktioniert bereits;
  der Fall sichert, dass die neue Draft-Sperre `prefer` nicht bricht).

Wesentliche Rot-Belege:

```
AssertionError: 'in-progress' != None : {'id': 'AP1', ...}
AssertionError: 'offen' == 'offen' : {'id': 'AP4', ...}
AssertionError: bin/vibe_issues.py fehlt (Backbone-Modul fuer den Issues-Sync)
```

### 3.2 Oberflächen/API/CLI

```
python3 -m unittest tests.unit.test_ap3_korbat_surfaces -v
```

Ergebnis: **Exit 1**, `Ran 23 tests`, `FAILED (failures=21)`.

- 21 Testmethoden scheitern (unbekannte Aktionen `issues.sync`/`issues.state`,
  fehlende Settings-Schlüssel, lokale AP-ID statt GH-Block, fehlende
  Nova-Marker für Draft/Ready, Draft-Standard bei der Ticket-Anlage).
- Bewusst grün (Opt-out-Regressionsschutz):
  `test_issues_sync_without_opt_in_makes_no_request`,
  `test_without_issue_sync_the_local_auto_id_is_kept`.

Wesentliche Rot-Belege:

```
Aktion unbekannt: "issues-state" (status|link|...|pr)
```

## 4. Setup-Defekte, die der Test-Agent selbst korrigiert hat

Vor dem dokumentierten Rotlauf wurden ausschließlich testseitige Defekte
gefunden und behoben; keine Assertion wurde abgeschwächt, um Grün zu erhalten:

1. **Doppelte `setUpClass`-Overrides** in den Web-Testklassen hätten die
   Token-Injektion der Basis-Fixture umgangen. Die Overrides wurden entfernt;
   die Klassen erben die gemeinsame Fixture mit `GITHUB_TOKEN`-Fake.
2. **Feature-Test** indizierte den Fake-POST, bevor das Fehlen des GH-Blocks
   geprüft war (irreführender `IndexError`). Jetzt wird zuerst der GH-Block
   assertiert, dann der POST geprüft.
3. **Idempotenz-Test** verlangte zunächst, dass der Titel eines lokalen
   `AP7`-Blocks unverändert bleibt. Design 4 erlaubt die Aktualisierung aus
   dem Remote-Stand; die Assertion prüft jetzt die Minimalforderung
   (ID bleibt, kein GH-Duplikat, Statusübernahme). Das ist eine Präzisierung
   auf das spezifizierte Soll, keine Abschwächung eines echten Verhaltens.
4. **Konflikttest** patchte nur `vibe_storage.write_text`; jetzt werden auch
   direkte Importe im Backbone-Modul erfasst, damit der Konfliktpfad
   unabhängig vom Importstil geprüft wird.
5. **`github`-Feld** wird auf `int(...)` geprüft, damit eine String- oder
   Integer-Repräsentation der Issuenummer beide dem Vertrag „Issuenummer“
   genügen.
6. **`created`-Statistik** verwendet einen Remote-Stand ohne geschlossenes
   Issue, damit die Anlage-Statistik nicht von der Interpretationsfrage
   „Closed ohne lokalen Block“ abhängt.
7. **Nachtrag Draft/Ready (15–21):** Die neuen Fälle wurden vor der
   Implementierung ergänzt. Zwei zunächst drohende `AttributeError` in den
   Draft-Ticket-Anlagen wurden durch eine vorgelagerte GH-Block-Assertion
   ersetzt, damit der Rotbefund die fehlende Funktion statt eines
   Folgefehlers zeigt. Der Reattach-Fall bleibt bewusst grün, weil `prefer`
   schon vor der Änderung funktioniert; er schützt die neue Draft-Sperre vor
   einer Regression.

## 5. Festgelegte Schnittstellen, die der Coding-Agent einhalten muss

Die Design-Entscheidungen nennen nicht alle JSON-/Feldnamen. Die Tests legen
diese naheliegenden, zu den Bestandsnamen passenden Verträge fest:

- `vibe_github.read_config`/`status`: `issues_enabled` (bool),
  `issues_in_progress_label` (str, Default `in-progress`),
  `issues_ready_label` (str, Default `ready`),
  `issues_assignee` (str, leer = alle).
- `project.env`: `GITHUB_ISSUES_ENABLED`, `GITHUB_ISSUES_IN_PROGRESS`,
  `GITHUB_ISSUES_READY`, `GITHUB_ISSUES_ASSIGNEE`.
- `/api/github action=settings`: `issues_enabled`, `issues_in_progress`,
  `issues_ready`, `issues_assignee`.
- `/api/github action=issues.sync`: Statistikschlüssel `created`, `updated`,
  `closed`, `pushed` irgendwo in der Antwort (auch verschachtelt zulässig).
- `/api/github action=issues.state`: `id` (z. B. `GH-101`) und `state`
  (`draft`/`ready`/`in-progress`/`open`), PATCH auf das Issue.
- `/api/ticket action=add`: `draft` (bool; bei aktivem Sync default Draft).
- CLI: `vibe github <projekt> issues-sync` und
  `issues-state <id> draft|ready|in-progress|open` (der bestehende
  Positionsparser muss das dritte Argument aufnehmen).
- `bin/vibe_packages.py`: `is_draft(block)` mit zeilenankerierter exakter
  `Status: draft`-Erkennung; `select_package` berücksichtigt sie in allen drei
  Auswahlwegen und lässt `prefer` gewinnen.
- `vibe_issues.sync_issues(project_path, config)` ist die zentrale
  Dienstfunktion; der Zustand ist pull-autoritativ (Ready/Draft/In-Progress/
  Closed).

## 6. Grenzen und verbleibende Lücken

- **Kein Browser/Playwright:** Nova wird nur strukturell über den JS-Quelltext
  geprüft (wie AP2/AP4). Echtes Rendering, Sichtbarkeit/Schalterzustände und
  Tastaturbedienung sind nicht automatisiert geprüft.
- **Kein echtes GitHub:** Die REST-Semantik wird gegen einen Loopback-Fake
  geprüft. Reale GitHub-Eigenheiten (Rate-Limits, Paginierung über 100 Issues
  hinaus, Label-/Assignee-Sonderfälle, Token-Scopes) sind nicht abgedeckt.
- **Token-Maskierung** in Fehlermeldungen/Logs wird nicht neu injiziert; sie
  ist Bestand der bestehenden `vibe_github`-Helper und wird von den
  B7/AP9-Tests abgedeckt. Die AP3-Tests verwenden nur Fake-Tokens.
- **Klassische UI** (`app.js`) wird bewusst nicht geprüft; Design 11 erklärt
  sie als unberührt.
- **Nicht im Umfang** (laut Arbeitspaket): automatisches In-Progress durch den
  Runner, GitHub-Priority-Anbindung, andere Kategorien als Bug/Feature.
- **Bestehende Aktionen** `issues`, `issues-import`, `pr`, `settings` werden
  nicht dupliziert getestet; ihr unverändertes Verhalten ist durch die
  vorhandene Suite (u. a. `test_ap9_github.py`, `test_ap4_korbat_*`) und den
  vollen Prüflauf abzusichern. Der neue Test
  `test_sync_ignores_the_legacy_github_label_filter` sichert ausdrücklich,
  dass der neue Sync `GITHUB_LABEL` nicht übernimmt.
- **Konflikttest** simuliert den Konflikt über die Storage-Schicht; ein echter
  paralleler Schreiber mit Timing ist nicht deterministisch und wird nicht
  verwendet.
- **Draft-Auswahl** wird an `vibe_packages.select_package` direkt geprüft,
  nicht über einen vollständigen Läuferlauf. Der Läufer ruft dieselbe Funktion
  auf; die Verdrahtung `select_package → Läufer` ist Bestand (AP11/AP4).
- **GitHub-Priority** und automatisches In-Progress durch den Runner bleiben
  laut Arbeitspaket außerhalb des Umfangs.

## 7. Testbefehle für Coding- und Review-Agent

```
python3 -m unittest tests.unit.test_ap3_korbat_issues_backend -v
python3 -m unittest tests.unit.test_ap3_korbat_surfaces -v
```

Erwartung nach der Implementierung: beide Module grün (`OK`, Exit 0), ohne
Abschwächung der Assertions. Die vier bzw. zwei bewusst vorher grünen
Regressionsfälle müssen grün bleiben.

## 8. Status

- Rotphase ausgeführt und dokumentiert (beide Module, Exit 1), inklusive des
  Nachtrags Draft/Ready (Design 15–21).
- Keine Produktionsdatei, kein bestehender Test und kein Prüfskript verändert.
- Grünprüfung nach der Implementierung ausgeführt; Ergebnis und
  Integritätsprüfung in §9.

## 9. Grünphase nach Implementierung (2026-11-22)

### 9.1 Ausgeführte Befehle und echte Ergebnisse

```
python3 -m unittest tests.unit.test_ap3_korbat_issues_backend -v
```

Ergebnis: **Exit 0**, `Ran 29 tests in 7.943s`, `OK` (29/29 grün, keine
Failures, keine Errors).

```
python3 -m unittest tests.unit.test_ap3_korbat_surfaces -v
```

Ergebnis: **Exit 0**, `Ran 23 tests in 10.042s`, `OK` (23/23 grün, keine
Failures, keine Errors).

Damit sind **52/52 Testfälle grün**. Die in §3 dokumentierten Rotphasen-Belege
bleiben unverändert erhalten; es wurden keine Assertions abgeschwächt,
übersprungen oder entfernt.

### 9.2 Integritätsprüfung der Testdateien

- `tests/unit/test_ap3_korbat_issues_backend.py`: **29** `test_*`-Methoden
  (unverändert), **125** Assertion-Aufrufe.
- `tests/unit/test_ap3_korbat_surfaces.py`: **23** `test_*`-Methoden
  (unverändert), **140** Assertion-Aufrufe.
- Keine `@unittest.skip`, keine `expectedFailure`, kein `skipTest`, keine
  Platzhalter (`assertTrue(True)`/`assertFalse(False)`).
- Stichproben der kritischen, nicht abschwächbaren Guards sind weiterhin
  vorhanden, u. a.:
  - `status == "in-progress"` und `github == 103` im Parser,
  - `Closes #77`/`Closes #551` im PR-Body sowie unveränderter Body ohne Bezug,
  - `Status: draft` und „Ready-Label fehlt“ bei Push/Ticket-Anlage,
  - `is_draft`-Semantik und Draft-Sperre in allen drei Auswahlwegen,
  - Assignee-Verbund (nur zugewiesen + ready wird gewählt),
  - Konfliktmeldung statt stillem Überschreiben,
  - Web-/CLI-Aktionen `issues-sync`, `issues.state`, `issues-state` und die
    Nova-Struktur (`issues-state`, `draft`, `category`, `issues_enabled`).
- `git status` zeigt die beiden Testdateien und den Bericht weiterhin als
  **untracked neu**; sie wurden nach der Rotphase nicht durch den
  Coding-Agenten angelegt oder verändert.

### 9.3 Erkennbare testfall-spezifische Sonderwege

Eine Quelltextsuche in den geänderten Produktionsdateien (`bin/vibe`,
`bin/vibe_github.py`, `bin/vibe-web.py`, `bin/vibe_packages.py`,
`bin/vibe_issues.py`, `bin/web/nova-project.js`, `bin/web/i18n.js`) nach
Testkennungen, Fake-Token und Fake-Issue-Nummern (`test_ap3`, `ap3-korbat`,
`GH-101`, `GH-102`, `GH-103`, `GH-105`, `GH-106`, `alice`, `FAKE_TOKEN`,
`FakeIssues`) lieferte **keine Treffer**. Eine inhaltliche Bewertung des
Implementierungsdiffs bleibt ausdrücklich dem Reviewer vorbehalten.


## 10. Review-Runde 1: Befundfälle (Rotphase)

Grundlage: `docs/reviews/AP3-Korbat-review-1.md` (Verdict
`CHANGES REQUIRED`, 1 High, 3 Medium, 1 Minor). Die Fälle leiten sich aus den
dort beschriebenen Verhaltensanforderungen ab, nicht aus einem Fix-Diff. Sie
wurden **vor** der Fehlerbehebung geschrieben und ausgeführt.

### 10.1 Befund 1 (High): Installer kennt `vibe_issues.py` nicht

Kein eigener Testfall ergänzt: Der Bestandsfall
`tests/unit/test_setup_vibe.py:318`
(`InstallFilesTest.test_every_module_imported_by_the_launcher_is_installed`)
leitet die vom Launcher importierten Module dynamisch per AST aus
`bin/vibe` ab und vergleicht sie mit `setup.PROGRAM_FILES`. Damit enthält er
`vibe_issues.py` automatisch, sobald der Import im Launcher steht — es gibt
keine gespiegelte, unabhängig zu pflegende Liste. Der zweite vom Reviewer
genannte Fall wurde ebenfalls ausgeführt.

Ausgeführt am 2026-11-22 (Stand vor der Behebung, Produktionscode unverändert
durch den Test-Agenten):

```
python3 -m unittest -v \
  tests.unit.test_setup_vibe.InstallFilesTest.test_every_module_imported_by_the_launcher_is_installed \
  tests.unit.test_setup_vibe.InstallFilesTest.test_installed_launcher_starts_with_all_options
```

Ergebnis: **Exit 1**, `Ran 2 tests`, `FAILED (failures=1, errors=1)`.

- `test_every_module_imported_by_the_launcher_is_installed`:
  `AssertionError: Lists differ: ['vibe_issues.py'] != []` →
  `Setup installiert nicht: vibe_issues.py`. Das ist der kausale AP3-Beleg.
- `test_installed_launcher_starts_with_all_options`: `ERROR`
  (`FileNotFoundError: .../_toolchain/bin`). Dieser Fall scheitert bereits an
  einer von AP3 unabhängigen Test-/API-Annahme derselben Klasse: Der Test ruft
  `install_program_files(kit, self.vibe, ...)` auf und erwartet die Dateien
  anschließend unter `self.vibe / "_toolchain"`, während die aktuelle
  Setup-Funktion direkt nach `vibe_root` installiert. Derselbe
  `_toolchain`-Pfadversatz ist bereits im B17-Bericht als vorbestehende
  Baseline dokumentiert (`docs/reviews/B17-test-agent-report.md`, Abschnitt
  „Baseline-Reds `test_setup_vibe`“); auch der nicht vom Reviewer genannte
  Nachbarfall `test_fresh_install_copies_programs_templates_and_catalog`
  scheitert unverändert (`AssertionError: False is not true : vibe`). Diese
  Baseline bleibt unangetastet und wird hier nur als Beobachtung gemeldet; die
  AP3-Kausalität ist durch den ersten Fall eindeutig belegt.

### 10.2 Befund 2 (Medium): Zeileninjektion über Issue-Body/Beschreibung

Zwei neue Fälle in `tests/unit/test_ap3_korbat_issues_backend.py`, Klasse
`DescriptionInjectionTest`. Gemeinsame Vorbedingung: Der Beschreibungstext
enthält harmlose Zeilen sowie `Status: ready`, `Status: draft`,
`Status: in-progress`, `GitHub: #999`, `Art: Bug`, `Priorität: P0`,
`Abhängigkeiten: AP1`, `BLOCKIERT: …`, `WARTET AUF MERGE: …` und
`Commit: deadbeef; Test: …`.

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_sync_pull_neutralizes_metadata_lines_from_issue_body` | Remote 201 (`ready`-Label) und 202 (kein Ready-Label), beide mit dem Injektions-Body | `sync_issues` | GH-201 ohne Statuszeile, GH-202 genau `Status: draft`; genau eine echte `GitHub:`-Zeile; kein `Art`/`Priorität`/`Abhängigkeiten`/`BLOCKIERT`/`WARTET`/`Commit` als Metazeile; Parser (`bin/vibe`), `_parse_block`, `is_draft/is_blocked/is_waiting_merge/priority/dependencies/proof_commits` reagieren nicht; Freitext bleibt lesbar |
| `test_add_ticket_connected_neutralizes_metadata_lines` | `add_ticket_connected` mit demselben Body, einmal `draft=False`, einmal `draft=True` | zwei Aufrufe | gleiche Entschärfung; ready-Block ohne Status, draft-Block mit `Status: draft`; echte Issuenummern 201/202 |

Rotausgabe:

```
python3 -m unittest tests.unit.test_ap3_korbat_issues_backend -v
→ Ran 32 tests, FAILED (failures=2), Exit 1
```

```
FAIL: test_sync_pull_neutralizes_metadata_lines_from_issue_body
AssertionError: 1 != 2 : - [ ] GH-201 Injected ready
  GitHub: #201
  Beschreibung: Erste Zeile bleibt lesbar
  Status: ready
  Status: draft
  Status: in-progress
  GitHub: #999
  Art: Bug
  Priorität: P0
  Abhängigkeiten: AP1
  BLOCKIERT: injiziert
  WARTET AUF MERGE: injiziert
  Commit: deadbeef; Test: injiziert
  Letzte Zeile bleibt lesbar
```

```
FAIL: test_add_ticket_connected_neutralizes_metadata_lines
AssertionError: 1 != 2 : (gleicher injizierter Block GH-201)
```

Geprüft wird bewusst nicht die exakte Escape-Syntax, sondern die Wirkung:
Kontrollzeilen-Zählung, echte Issuenummer, echter Zustand, keine
Läufer-Marker und kein fingierter Nachweis; die harmlosen Textzeilen und die
Injektionswörter bleiben im Block lesbar.

### 10.3 Befund 3 (Medium): „In Progress“-Pille ohne `nv-warn`

Neuer Fall in `tests/unit/test_ap3_korbat_surfaces.py`, Klasse
`NovaIssuesSurfaceTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_in_progress_pill_uses_warn_class_and_draft_stays_muted` | `nvpBoardColumn` in `nova-project.js` | Klassenzuweisung der Pille prüfen | Die `nv-warn`-Bedingung enthält `In Progress`; `Draft` erhält weiterhin `nv-muted` |

Rotausgabe:

```
FAIL: test_in_progress_pill_uses_warn_class_and_draft_stays_muted
AssertionError: False is not true : In Progress erhaelt kein nv-warn:
["el('span', {class: 'nv-pill nv-state' + (row.state === 'WARTET AUF MERGE' ?
' nv-warn' : row.state === 'Draft' ? ' nv-muted' : '')}, ..."]
```

### 10.4 Befund 4 (Medium): Legacy-`GH-<n>`-Karten ohne Zustandsaktionen

Neue Fälle:

| Testfall | Datei | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|---|
| `test_cards_with_gh_id_without_reference_get_state_actions` | `test_ap3_korbat_surfaces.py` | `nvpBoardColumn`, Karte mit ID `GH-<n>` ohne `GitHub:`-Zeile | Gate der Aktionen prüfen | `issues-state` bleibt; Gate akzeptiert zusätzlich `/^GH-\d+$/` (neben `row.github`) |
| `test_gh_id_without_reference_keeps_github_none` | `test_ap3_korbat_issues_backend.py` | Legacy-Block `GH-77` ohne `GitHub: #77` | `ticket_items` | `id == GH-77`, `github is None`, `status` leer — der Parser erfindet keine Nummer |

Rotausgabe des Strukturfalls:

```
FAIL: test_cards_with_gh_id_without_reference_get_state_actions
AssertionError: Regex didn't match: '\^GH-\\d\+\$' not found in
"... var issueActions = (issuesEnabled && !isFeedback && (row.github != null)) ..."
```

Der verhaltensseitige Parserfall ist bereits vor der Behebung grün (er
schützt den Vertrag `github is None` für Legacy-Blöcke).

### 10.5 Oberflächen-Rotlauf gesamt

```
python3 -m unittest tests.unit.test_ap3_korbat_surfaces -v
→ Ran 25 tests, FAILED (failures=2), Exit 1
```

### 10.6 Fallzahlen und Integrität

- `test_ap3_korbat_issues_backend.py`: **32** Fälle (vorher 29; +3).
- `test_ap3_korbat_surfaces.py`: **25** Fälle (vorher 23; +2).
- Gesamt: **57**.
- Keine Bestandstestdatei geändert, keine bestehende Assertion abgeschwächt,
  keine Produktionsdatei durch den Test-Agenten verändert.

## 11. Fix-Verifikation Review-Runde 1 (Grünphase)

Datum: 2026-11-22. Die Review-Befunde sind implementiert. Zwei testseitige
Nachzüge lagen ausschließlich in der Verantwortung des Test-Agenten und wurden
hier korrigiert; **keine Assertion wurde abgeschwächt und kein erwartetes
Verhalten umgeschrieben**.

### 11.1 Testseitige Korrektur 1: `_scan_blocks`-Aufruf

`tests/unit/test_ap3_korbat_issues_backend.py`, `DescriptionInjectionTest`
(`assert_neutralized`): Der neue Fall übergab `block.splitlines()` an
`bin/vibe._scan_blocks`. Diese Funktion erwartet jedoch den vollständigen Text
und ruft selbst `text.splitlines()` auf; die Liste erzeugte
`AttributeError: 'list' object has no attribute 'splitlines'`.

Korrektur: `cli._scan_blocks(block)` (Text statt Liste). Begründung: reine
API-Korrektur eines vom Test-Agenten neu eingeführten Setup-Defekts; die
Assertions und das erwartete Entschärfungsverhalten bleiben unverändert. Die
beiden `DescriptionInjectionTest`-Fälle laufen danach gegen die implementierte
`_neutralize_description_line`-Logik und sind grün.

### 11.2 Testseitige Korrektur 2: gespiegelte `PROGRAM_FILES`

Die Bestands-Fixtures spiegeln die Installer-Dateiliste in eigenen
`PROGRAM_FILES`-Tupeln für ihre `make_kit`-Quellverzeichnisse. Sie enthielten
`vibe_issues.py` noch nicht, obwohl die Produktionsliste
(`scripts/setup-vibe.py`) es nach `vibe_github.py` führt. Dadurch schlugen die
Fixtures mit `SetupError: Unvollständiges Quellverzeichnis: …/bin/vibe_issues.py
fehlt` fehl.

Angepasst (Eintrag `vibe_issues.py` an derselben Stelle wie in der
Produktionsliste, direkt nach `vibe_github.py`):

- `tests/unit/test_setup_vibe.py` (Modul-`PROGRAM_FILES`, Zeile 47)
- `tests/unit/test_install_lifecycle.py` (Modul-`PROGRAM_FILES`, Zeile 40)
- `tests/unit/test_b17_isolation.py` (Modul-`PROGRAM_FILES`, Zeile 71)

Begründung: Der Spiegel muss der realen Installer-Liste entsprechen (genau das
verlangt der Reviewer-Hinweis zu Befund 1). Der Assertionstyp bleibt
unverändert; es wurde keine Prüfung entfernt oder gelockert. Der kausale
Installer-Fall `test_every_module_imported_by_the_launcher_is_installed` ist
damit grün.

### 11.3 Grünlauf a) — AP3-Testmodule

```
python3 -m unittest tests.unit.test_ap3_korbat_issues_backend tests.unit.test_ap3_korbat_surfaces -v
```

Ergebnis: **Exit 0**, `Ran 57 tests in 18.948s`, `OK` (57/57 grün). Darin
enthalten: beide `DescriptionInjectionTest`-Fälle,
`test_gh_id_without_reference_keeps_github_none`,
`test_in_progress_pill_uses_warn_class_and_draft_stays_muted` und
`test_cards_with_gh_id_without_reference_get_state_actions`.

### 11.4 Grünlauf b) — `test_setup_vibe`

```
python3 -m unittest tests.unit.test_setup_vibe -v
```

Ergebnis: **Exit 1**, `Ran 50 tests in 0.587s`,
`FAILED (failures=6, errors=4)`.

Grün ist insbesondere der kausale AP3-Fall:

```
test_every_module_imported_by_the_launcher_is_installed ... ok
```

Die verbleibenden 10 Rotfälle sind **exakt** die im B17-Bericht dokumentierte
Baseline (`docs/reviews/B17-test-agent-report.md`, Abschnitt „Baseline-Reds
`test_setup_vibe` (6 Failures, 4 Errors)“); zusätzlich nennt
`docs/features/AP5-Korbat.md` §5 `test_setup_vibe` als vorbestehende
Umgebungs-/Drift-Familie.

Failures (6, `_toolchain`-Pfadversatz bzw. Launcher-Erwartung):

- `test_fresh_install_copies_programs_templates_and_catalog`
- `test_missing_catalog_is_a_warning_not_an_abort`
- `test_reuse_keeps_existing_programs_and_only_adds_missing_ones`
- `test_update_backs_up_changed_programs_and_templates`
- `test_posix_launcher_is_a_symlink_to_the_installed_program`
  (`…/Vibe/bin/vibe` vs. `…/Vibe/_toolchain/bin/vibe`)
- `test_windows_launcher_starts_the_python_program`
  (`'_toolchain\\bin\\vibe' not found`)

Errors (4):

- `test_installed_launcher_starts_with_all_options`
  (`FileNotFoundError: …/_toolchain/bin`, derselbe Pfadversatz)
- `test_existing_and_new_projects_receive_the_test_agent`
- `test_existing_project_configuration_is_kept_and_new_projects_are_registered`
- `test_register_projects_keeps_an_existing_test_agent`
  (je `TypeError: register_projects() missing 1 required positional argument:
  'install'`)

Keiner dieser Fälle berührt AP3-Codeflächen; die Zahl 6 Failures/4 Errors
stimmt mit der dokumentierten Baseline überein.

### 11.5 Grünlauf c) — `test_install_lifecycle` + `test_b17_isolation`

```
env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_install_lifecycle tests.unit.test_b17_isolation -v
```

Ergebnis: **Exit 1**, `Ran 55 tests in 0.563s`,
`FAILED (failures=7, errors=28)`.

Modulweise:

- `tests.unit.test_b17_isolation`: `Ran 12 tests`, **OK**.
- `tests.unit.test_install_lifecycle`: `Ran 43 tests`,
  `FAILED (failures=7, errors=28)` — genau die B17-Baseline
  (`docs/reviews/B17-test-agent-report.md`: 28 Errors `FileNotFoundError` aus
  dem `install()`-Helfer wegen `install_program_files(kit, self.vibe)`
  gegenüber `self.toolchain`; 7 Assertion-Failures aus demselben
  Pfadversatz). Fehlersignaturen im Lauf: **28× `FileNotFoundError`,
  7× `AssertionError`**; keine andere Fehlerart.

Failures (7):

- `test_fresh_install_copies_all_program_modules_and_writes_version`
- `test_plan_lists_new_changed_and_unchanged_files`
- `test_uninstall_preview_does_not_require_yes`
- `test_uninstall_refuses_while_a_run_is_live`
- `test_uninstall_removes_only_its_own_launcher_symlink`
- `test_uninstall_reports_every_removed_launcher`
- `test_uninstall_requires_yes_without_terminal`

Errors (28, alle `FileNotFoundError` aus demselben `_toolchain`-Pfadversatz):
`test_aborted_update_restores_previous_files_and_keeps_backup`,
`test_backup_failure_is_reported_as_setup_error_and_changes_nothing`,
`test_cli_rollback_restores_the_previous_installation`,
`test_force_allows_the_update_of_a_running_installation`,
`test_force_bypasses_the_guard_of_a_live_session`,
`test_launcher_failure_restores_the_previous_installation`,
`test_missing_permissions_do_not_leave_a_partial_install`,
`test_reuse_failure_keeps_the_version_of_an_untouched_installation`,
`test_reuse_keeps_user_templates_and_programs`,
`test_reuse_on_an_empty_target_records_the_version`,
`test_rollback_refuses_while_a_run_is_live`,
`test_rollback_rejects_a_backup_with_parent_paths`,
`test_rollback_restores_programs_templates_and_version`,
`test_rollback_without_backup_fails_without_changes`,
`test_select_backup_ignores_uninstall_backups`,
`test_select_backup_orders_numeric_suffixes_numerically`,
`test_uninstall_backs_up_changed_templates_before_removal`,
`test_uninstall_removes_programs_and_templates_but_keeps_runtime_and_projects`,
`test_update_backs_up_program_and_user_template_and_keeps_runtime`,
`test_update_proceeds_when_a_running_record_has_no_session`,
`test_update_proceeds_when_a_starting_record_has_no_session`,
`test_update_records_version_commit_and_source`,
`test_update_refuses_conservatively_when_tmux_is_unavailable`,
`test_update_refuses_when_the_run_state_is_unreadable`,
`test_update_refuses_while_a_run_is_live`,
`test_update_refuses_while_a_starting_run_is_live`,
`test_update_without_changed_files_still_records_the_new_version`,
`test_verify_installation_reports_a_missing_web_asset`.

Die vom Auftrag genannten Vorher-Zahlen (12 Failures/35 Errors) wurden durch
den fehlenden Spiegel-Eintrag verursacht; nach der Anpassung bleibt
ausschließlich die dokumentierte Baseline rot. Es gibt **keinen neuen,
AP3-kausalen Rotfall**.

### 11.6 Fazit

- AP3-Fallbestand: **57/57 grün**.
- Kausaler Befund-1-Fall grün.
- Verbleibende Rotfälle in den Installer-Modulen sind namentlich der
  B17-/AP5-Baseline zugeordnet (Pfadversatz `_toolchain`, `register_projects`-
  Signatur); keine Abschwächung, keine AP3-Regression.

## 12. Bestandstest-Fortschreibung (Volllauf-Abgleich AP3)

Datum: 2026-11-22. Der Volllauf (2302 Tests, 36 rote Module) wurde gegen die
dokumentierte Baseline abgeglichen:

- **35 rote Module = vorbestehende Baseline.**
  - 33 Module decken sich mit der AP5-Klassifizierung
    (`docs/features/AP5-Korbat.md` §5).
  - Zusätzlich `test_ap8_github_checkout.LocalAdoptionTest.test_the_shipped_test_agent_is_replaced_by_the_local_template`
    und `test_verify_script.RepositoryVerifyTest.test_repository_quick_check_passes`;
    beide wurden am Ausgangsstand `6449438` per git-archive-Export mit
    identischer `project.env` und identischer Fehlersignatur reproduziert und
    sind damit nachweislich nicht AP3-verursacht.
- **Genau 1 Fall = beabsichtigte AP3-Vertragsänderung**, der als Bestandstest
  fortgeschrieben wurde (siehe 12.1).

### 12.1 Geänderter Bestandstest

Datei/Klasse/Fall:
`tests/unit/test_ap5_korbat_waiting_state.py`,
`NovaWaitingSurfaceTest.test_nova_board_orders_the_waiting_column_between_open_and_blocked`
(Zeile 547 ff.).

Alter Vertrag (bis AP5): `['open', 'waiting', 'blocked', …]`.
Neuer AP3-Vertrag (`bin/web/nova-project.js:1113`):
`['open', 'progress', 'draft', 'waiting', 'blocked', 'proof', 'done']`.

Neuer Assertionstext (vollständige, scharfe Reihenfolge; keine Aufweichung auf
„waiting irgendwo“):

```python
# AP3-Board-Vertragsänderung: 'progress' (In Progress) und 'draft'
# (Entwurf) sind vor 'waiting' neu; die Wartet-Spalte bleibt zwischen
# den Arbeitszuständen und 'blocked'.
self.assertRegex(
    self.text,
    r"\[\s*'open'\s*,\s*'progress'\s*,\s*'draft'\s*,\s*'waiting'"
    r"\s*,\s*'blocked'\s*,\s*'proof'\s*,\s*'done'\s*\]",
    "Keine Spaltenfolge open → progress → draft → waiting → blocked "
    "→ proof → done",
)
```

Die Absicht des Bestandsfalls bleibt erhalten: Die Wartet-auf-Merge-Spalte
liegt weiterhin nach den Arbeitszuständen (offen/in progress/entwurf) und vor
`blocked`. Es wurde keine andere Testdatei und keine andere Assertion
angefasst.

### 12.2 Ausführungsergebnisse

```
env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap5_korbat_waiting_state -v
```

Ergebnis: **Exit 0**, `Ran 23 tests in 0.510s`, `OK` (23/23 grün).

```
env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap3_korbat_issues_backend tests.unit.test_ap3_korbat_surfaces -v
```

Ergebnis: **Exit 0**, `Ran 57 tests in 18.964s`, `OK` (57/57 grün,
Unversehrtheit der AP3-Module).

```
env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap5_korbat_waiting_state tests.unit.test_ap8_github_checkout tests.unit.test_verify_script -v
```

Ergebnis: **Exit 1**, `Ran 90 tests in 9.726s`,
`FAILED (failures=2)` — **nur** die beiden am Ausgangsstand reproduzierten
Vorlast-Fälle:

- `test_ap8_github_checkout.LocalAdoptionTest.test_the_shipped_test_agent_is_replaced_by_the_local_template`
  (`'# Mitgelieferter V99' != 'LOKALER-PRUEFAGENT-STAND-4711'`)
- `test_verify_script.RepositoryVerifyTest.test_repository_quick_check_passes`
  (`'import-manifest' not found` in der quick-Prüfausgabe)

Damit ist die Abgleichslogik bestätigt: 36 rote Module = 35 vorbestehende
Baseline + 1 fortgeschriebener Bestandstest; keine Abschwächung, keine
zusätzliche AP3-Regression.
