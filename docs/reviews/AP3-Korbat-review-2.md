# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Verifikation der Befunde aus Runde 1

1. **[High] `scripts/setup-vibe.py:64` — Neues Modul `vibe_issues.py` fehlt in `PROGRAM_FILES` des Installers**
   - **Behoben: ja**
   - **Beleg:** In `scripts/setup-vibe.py:64` ist `"vibe_issues.py"` in `PROGRAM_FILES` direkt nach `"vibe_github.py"` eingetragen. Analog dazu hat der unabhängige Test-Agent die gespiegelten `PROGRAM_FILES`-Fixtures in `tests/unit/test_setup_vibe.py:47`, `tests/unit/test_install_lifecycle.py:40` und `tests/unit/test_b17_isolation.py:71` aktualisiert (`docs/reviews/AP3-Korbat-test-agent-report.md` §11.2). Der kausale AST-Wächter `test_every_module_imported_by_the_launcher_is_installed` sowie `test_b17_isolation` (12/12) sind im dokumentierten Lauf grün (`docs/reviews/AP3-Korbat-test-agent-report.md` §§11.4, 11.5); die verbleibenden Rotfälle in `test_setup_vibe` (6 Failures, 4 Errors) und `test_install_lifecycle` (7 Failures, 28 Errors) sind stichhaltig und namentlich der vorbestehenden B17-Baseline (`_toolchain`-Pfadversatz und `register_projects`-Signatur) zugeordnet.

2. **[Medium] `bin/vibe_issues.py:39-53,281-310` — Zeileninjektion über mehrzeilige Issue-Bodies/Beschreibungen in `TICKETS.md`**
   - **Behoben: ja**
   - **Beleg:** `_META_KEYS` (`bin/vibe_issues.py:39-44`, deckungsgleich mit `_FEEDBACK_LABEL` in `bin/vibe:604-606`), `_CONTROL_LINE` (`bin/vibe_issues.py:50-52`, `re.IGNORECASE`) und `_neutralize_description_line` (`bin/vibe_issues.py:281-296`, aufgerufen in `_build_block` Zeile 309 für beide Schreibwege `sync_issues` und `add_ticket_connected`) entschärfen jede Beschreibungs-Folgezeile, die mit einem der 19 Schlüsselwörter plus Doppelpunkt beginnt. Die bewusste Design-Entscheidung, neben dem `> `-Präfix auch Schlüsselwort und Doppelpunkt zu trennen (`Status: ready` → `  > Status ready`), ist technisch notwendig und begründet: Ein bloßes `> `-Präfix hätte Substring- und `.search()`-Prüfungen in `bin/vibe_packages.py` (`is_blocked` auf `"BLOCKIERT:" in block.upper()`, `is_waiting_merge` auf `"WARTET AUF MERGE:" in block.upper()`, `priority` auf `Priorität\s*:\s*(P\d)`, `dependencies` auf `Abhängigkeiten\s*:\s*(.+)`) nicht neutralisiert. Durch das Entfernen des Doppelpunkts nach dem Schlüsselwort und das Voranstellen von `> ` schlagen weder `_FEEDBACK_LABEL`/`_META_LINE`/`_STATUS_LINE`/`_GITHUB_REF`/`_ART_LINE` noch `is_draft`, `is_blocked`, `is_waiting_merge`, `priority`, `dependencies` oder `proof_commits` (`^[ \t]*Commit\s*:`) an, während der Text im Block lesbar bleibt. Abgesichert durch `DescriptionInjectionTest` (`tests/unit/test_ap3_korbat_issues_backend.py:1008-1144`, 2 Fälle, rot vor Fix, grün nach Fix).

3. **[Medium] `bin/web/nova-project.js:183` — Status-Pille für `In Progress` hat in Nova keine gelbe Hervorhebung (`nv-warn`)**
   - **Behoben: ja**
   - **Beleg:** In `bin/web/nova-project.js:183` lautet die Klassenzuweisung nun `'nv-pill nv-state' + ((row.state === 'WARTET AUF MERGE' || row.state === 'In Progress') ? ' nv-warn' : row.state === 'Draft' ? ' nv-muted' : '')`. Damit erhält `'In Progress'` die gelbe Klasse `nv-warn`, `'Draft'` weiterhin die graue Klasse `nv-muted`. Abgesichert durch `test_in_progress_pill_uses_warn_class_and_draft_stays_muted` (`tests/unit/test_ap3_korbat_surfaces.py:729-745`).

4. **[Medium] `bin/web/nova-project.js:163` — Ticketkarten mit ID `GH-<n>` ohne `GitHub: #<n>`-Zeile erhalten keine Zustandsaktionen (`issues-state`)**
   - **Behoben: ja**
   - **Beleg:** In `bin/web/nova-project.js:163` prüft das Gate für `issueActions` nun `(issuesEnabled && !isFeedback && (row.github != null || /^GH-\d+$/.test(id)))`. Gleichzeitig bleibt in `bin/vibe:635-652` `row["github"]` für Legacy-Blöcke ohne `GitHub: #<n>`-Zeile unverändert `None`. Abgesichert durch `test_cards_with_gh_id_without_reference_get_state_actions` (`tests/unit/test_ap3_korbat_surfaces.py:747-760`) und `test_gh_id_without_reference_keeps_github_none` (`tests/unit/test_ap3_korbat_issues_backend.py:1326-1344`).

5. **[Minor] `docs/import-manifest.json:1239-1254` — Kein `aenderungen`-Eintrag für `AP3-Korbat` im Import-Manifest**
   - **Behoben: ja**
   - **Beleg:** `docs/import-manifest.json:1239-1254` enthält nun den vollständigen `aenderungen`-Eintrag für `"arbeitspaket": "AP3-Korbat"` mit Datum `2026-11-22`, allen 9 betroffenen Dateien (`bin/vibe`, `bin/vibe-web.py`, `bin/vibe_github.py`, `bin/vibe_packages.py`, `bin/vibe_issues.py`, `bin/web/i18n.js`, `bin/web/nova-project.js`, `scripts/setup-vibe.py`, `docs/import-manifest.json`) und ausführlicher Begründung; die `"files"`-Einträge (`bin/vibe_issues.py`: Zeile 1308, `bin/web/nova-project.js`: Zeile 1418, `scripts/setup-vibe.py`: Zeile 1448) sind auf dem aktuellen Stand.

## Audit der testseitigen Änderungen
- Alle testseitigen Änderungen wurden durch den unabhängigen Test-Agenten vorgenommen und in `docs/reviews/AP3-Korbat-test-agent-report.md` §§10–11 dokumentiert.
- Keine bestehende Assertion in `tests/unit/test_ap3_korbat_issues_backend.py` (jetzt 32 Fälle) oder `tests/unit/test_ap3_korbat_surfaces.py` (jetzt 25 Fälle) wurde abgeschwächt oder entfernt.
- Die Korrektur `cli._scan_blocks(block)` in `tests/unit/test_ap3_korbat_issues_backend.py:1045` behebt ausschließlich die Aufrufsignatur (`_scan_blocks` in `bin/vibe:526` erwartet `str` statt `list[str]`); alle Assertions in `assert_neutralized` prüfen unverändert scharf gegen Parser und Läufer-Marker.
- Die Ergänzung von `"vibe_issues.py"` in den `PROGRAM_FILES`-Tupeln von `tests/unit/test_setup_vibe.py:47`, `tests/unit/test_install_lifecycle.py:40` und `tests/unit/test_b17_isolation.py:71` spiegelt lediglich die reale Produktionsliste für `make_kit()`.

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| 1. Opt-in: nur exakt `GITHUB_ISSUES_ENABLED="1"` aktiviert jegliches Issue-Verhalten; ohne Opt-in kein Netz, keine Format-/ID-Änderung | PASS | `bin/vibe_github.py:458`, `bin/vibe-web.py:1638,1863,1873`, `bin/vibe:1171,1184` | `IssuesConfigTest`, `IssuesSyncApiTest`, `TicketAddApiTest`, `IssuesCliTest` (`docs/reviews/AP3-Korbat-test-agent-report.md` §§2.1, 2.6, 2.7, 2.8, 11.3: 57/57 OK). |
| 2. `read_config`/`status`: `issues_enabled` (binär), `issues_in_progress_label` (Default `"in-progress"`), `issues_ready_label` (Default `"ready"`), `issues_assignee` (leer=alle) | PASS | `bin/vibe_github.py:458-473,806-809` | `IssuesConfigTest` (4/4 OK). |
| 3. Backbone `bin/vibe_issues.py`: kompletter REST-Zugriff nur dort über `vibe_github`-Helper; UI/CLI nur Dienstfunktionen; keine Tokens in Meldungen/Logs; in `setup-vibe.py` installiert | PASS | `bin/vibe_issues.py:1-127`, `scripts/setup-vibe.py:64` | `test_backbone_module_uses_vibe_github_for_rest`, `test_every_module_imported_by_the_launcher_is_installed` (`docs/reviews/AP3-Korbat-test-agent-report.md` §§2.2, 11.4: OK). |
| 4. Pull: offene Issues → `- [ ] GH-<n> <Titel>` (+ entschärfte Beschreibung bei Neuanlage, `GitHub: #<n>`, `bug` → `Art: Bug`); Match über `GH-<n>` oder Verweiszeile; keine Duplikate; zustands-/titelautoritativ; Beschreibung nur bei Neuanlage; ignoriert `GITHUB_LABEL`; Legacy `issues`/`issues-import` unverändert | PASS | `bin/vibe_issues.py:39-53,63-98,281-390` | `IssuesSyncTest` + `DescriptionInjectionTest` (`docs/reviews/AP3-Korbat-test-agent-report.md` §§2.2, 10.2, 11.3: OK). |
| 5. Push: offene lokale Blöcke ohne GitHub-Bezug → Issue anlegen (`Art: Bug` → Label `bug`) mit Zustandstreue (ohne Statuszeile → mit Ready-Label; `Status: draft` → ohne), danach Verweiszeile; lokale ID bleibt; `[x]` und `FEEDBACK.md` werden nicht gepusht | PASS | `bin/vibe_issues.py:392-413` | `test_push_creates_issues_for_open_local_packages_only`, `test_push_preserves_draft_and_ready_state` (OK). |
| 6. Draft/Läufer-Filter: `is_draft` (exakt zeilenankerierte `Status: draft`-Zeile) in `select_package` über alle drei Auswahlwege; „draft“ in Beschreibungstext ist kein Draft; `prefer` (Reattach) gewinnt | PASS | `bin/vibe_packages.py:413-418,704-740` | `DraftSelectionTest` (5/5 OK) + `test_assignee_and_draft_compose_for_work_selection` (OK). |
| 7. State-Aktion: API `issues.state` (`id`, `state`) + CLI `issues-state <id> draft\|ready\|in-progress\|open` — Label-PATCH auf GitHub + sofortige lokale Statuszeilen-Synchronisation | PASS | `bin/vibe_issues.py:431-498`, `bin/vibe-web.py:1871-1878`, `bin/vibe:1180-1190,1331-1337,1351-1384` | `IssuesSyncApiTest`, `IssuesCliTest` (OK). |
| 8. Sync-Aktion: `issues.sync` (API) + `issues-sync` (CLI): Pull+Push+Close mit Statistik (`created`/`updated`/`closed`/`pushed`); ohne Opt-in klare Meldung, kein Netz | PASS | `bin/vibe_issues.py:319-423`, `bin/vibe-web.py:1859-1870`, `bin/vibe:1167-1178,1327-1330` | `IssuesSyncApiTest`, `IssuesCliTest` (OK). |
| 9. PR-Body: `complete_package` hängt bei Issue-Bezug (`GH-<n>` oder `GitHub: #n`) `Closes #<n>` an; ohne Bezug unverändert | PASS | `bin/vibe_github.py:1155-1190,1238-1241` | `CompletePackageClosesIssueTest` (3/3 OK). |
| 10. Ticket-Anlage verbunden: `/api/ticket add` mit `category` (`bug`\|`feature`) und `draft` (Standard: Entwurf) → Issue zuerst, Block `GH-<n>` + `GitHub: #n` (+ `Status: draft` bei Entwurf); REST-Fehler → verständliche Meldung, kein halbfertiger Eintrag; ohne Sync exakt Altverhalten | PASS | `bin/vibe_issues.py:501-550`, `bin/vibe-web.py:1631-1648` | `TicketAddApiTest` (6/6 OK) + `test_add_ticket_connected_neutralizes_metadata_lines` (OK). |
| 11. Settings: `issues_enabled`/`issues_in_progress`/`issues_ready`/`issues_assignee` mit Validierung (Label ohne Zeilenumbrüche; Assignee ohne Steuerzeichen/Slash; binär wie `auto_merge`) | PASS | `bin/vibe-web.py:1780-1797` | `IssuesSettingsApiTest` (2/2 OK). |
| 12. Nova-UI: Pillen In Progress (gelb `nv-warn`)/Entwurf (grau `nv-muted`), Sync-Button `issues-sync`, Zustandsaktionen `issues-state` (für `row.github != null` und `GH-<n>`), Draft-Checkbox + Kategorie-Select im Formular, GitHub-Karte-Schalter/-Felder; i18n-Keys; klassische UI unberührt | PASS | `bin/web/nova-project.js:53-73,163-183,243-253,635-648,794-800,1052-1065,1111-1120`, `bin/web/i18n.js:1024-1035,2048-2058` | `NovaIssuesSurfaceTest` (9/9 OK, inkl. `test_in_progress_pill_uses_warn_class_and_draft_stays_muted` und `test_cards_with_gh_id_without_reference_get_state_actions`). |
| 13. Parser: `Status:` additiv; `ticket_items` führen `status`/`github`; Präzedenz `erledigt > BLOCKIERT > WARTET AUF MERGE > In Progress > Draft > offen`; `FEEDBACK.md`-Parsing bleibt funktionsfähig; Bestandsfelder unverändert | PASS | `bin/vibe:604-683,702-704` | `TicketParserTest` (6/6 OK, inkl. `test_gh_id_without_reference_keeps_github_none`). |
| 14. Speicherweg: `TICKETS.md` ausschließlich über `vibe_storage` atomar mit `expected` Digest; Konflikt → Meldung, nie still überschreiben | PASS | `bin/vibe_issues.py:328,418-422,459,493-497,531,545-549` | `test_conflicting_ticket_change_is_reported_not_overwritten` (OK). |

## Findings
- No findings.

## Verification
- Change set reviewed: Alle geänderten und neuen Dateien der Runde 2 (`scripts/setup-vibe.py`, `bin/vibe_issues.py`, `bin/web/nova-project.js`, `docs/import-manifest.json`, `docs/features/AP3-Korbat.md`, `docs/reviews/AP3-Korbat-test-agent-report.md`, `tests/unit/test_ap3_korbat_issues_backend.py`, `tests/unit/test_ap3_korbat_surfaces.py`, `tests/unit/test_setup_vibe.py`, `tests/unit/test_install_lifecycle.py`, `tests/unit/test_b17_isolation.py`) direkt über `read` inspiziert.
- Git commands run by me: none (kein Shell-/Git-Werkzeug in dieser Reviewer-Umgebung verfügbar).
- Checks evidenced by supplied raw output (`docs/reviews/AP3-Korbat-test-agent-report.md` §§10–11):
  - `python3 -m unittest tests.unit.test_ap3_korbat_issues_backend tests.unit.test_ap3_korbat_surfaces -v` → `Ran 57 tests in 18.948s`, `OK` (57/57 grün; Rotphase der neuen Befundfälle vor dem Fix in §10 dokumentiert).
  - `python3 -m unittest tests.unit.test_setup_vibe -v` → `Ran 50 tests in 0.587s`, `FAILED (failures=6, errors=4)`; `test_every_module_imported_by_the_launcher_is_installed ... ok`; alle 10 Rotfälle vorbestehende B17-Baseline.
  - `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_install_lifecycle tests.unit.test_b17_isolation -v` → `test_b17_isolation`: `Ran 12 tests`, `OK`; `test_install_lifecycle`: `Ran 43 tests`, `FAILED (failures=7, errors=28)` (ausschließlich vorbestehende B17-Baseline).
- Checks reported only by the coding agent:
  - `python3 scripts/check-syntax.py` → Exit 0.
  - `python3 scripts/check-no-secrets.py` → Exit 0.
  - `python3 scripts/check-import-manifest.py` → Exit 0 (68 Dateien).
  - `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh quick` → Exit 0.
- Checks not independently run: alle Build-, Test- und Git-Befehle (aufgrund der read-only Reviewer-Rolle ohne Shell-Tool).
- Important areas inspected: `scripts/setup-vibe.py:43-66`, `bin/vibe_issues.py:30-55,280-315`, `bin/web/nova-project.js:160-190`, `docs/import-manifest.json:1239-1455`, `docs/reviews/AP3-Korbat-test-agent-report.md:409-728`, `tests/unit/test_ap3_korbat_issues_backend.py:986-1145,1326-1345`, `tests/unit/test_ap3_korbat_surfaces.py:729-760`, `tests/unit/test_setup_vibe.py:26-49`, `tests/unit/test_install_lifecycle.py:19-42`, `tests/unit/test_b17_isolation.py:50-73`.
- Remaining risks:
  - `docs/features/AP3-Korbat.md` nennt in §2 (`530 Zeilen`) und §5 (`29`/`23`/`52/52` Testfälle, `7 AP3-Produktionsdateien`) noch die Zahlen aus Runde 1 vor den 5 neuen Befundfällen (jetzt 32/25 = 57/57 Fälle, 550 Zeilen in `bin/vibe_issues.py`, 8 Produktionsdateien inkl. `scripts/setup-vibe.py`); eine kurze Aktualisierung dieser Zahlen in `docs/features/AP3-Korbat.md` vor dem Abschluss-Commit wird empfohlen, blockiert das `PASS` aber nicht.
  - Der einmalige Gesamtlauf `scripts/verify.sh full` vor Paketabnahme steht wie geplant noch aus.
