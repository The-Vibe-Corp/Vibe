# Review GH-48 — Runde 2 (unabhängiger Review-Agent)

Bezug: Review Runde 1 (`docs/reviews/GH-48-review-1.md`, `Verdict: CHANGES REQUIRED`), Startcommit `ad00c0b`, Branch `feature/korbat/gh-48`.

## 1. Zusammenfassung des Änderungssatzes

Der Änderungssatz für **GH-48 „Improve ticket system"** (`ad00c0b..working tree`, 51 geänderte getrackte Dateien inkl. `bin/web/i18n.js`, 2 gelöschte Vorlagen-Ledger, 10 neue ungetrackte Dateien inkl. `docs/reviews/GH-48-review-1.md`) ersetzt die getrennten Markdown-Ledger `TICKETS.md` und `FEEDBACK.md` vollständig durch den einheitlichen, maschinenlesbaren und unversionierten Ticketspeicher `.vibe/tickets.json` (`bin/vibe_tickets.py`) sowie den Einzeldatei-Transport `TICKET-<ID>.json` im Runner. Alle sechs Befunde aus Runde 1 (1 High, 2 Medium, 3 Minor) wurden präzise, rückstandsfrei und ohne neue Regressionsflächen behoben; die zugehörigen Testverträge wurden vom unabhängigen Test-Agenten in Runde 4 (`docs/reviews/GH-48-test-agent-report.md` §10) auf exakte Meldungsprüfungen und die bereinigte Standardordnung nachgezogen.

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## 2. Prüfung der Behebungen aus Runde 1

1. **[High] `bin/vibe-web.py:1790-1794` — Doppeltes Präfix (`BB1`/`FF1`) bei `POST /api/feedback` (`action=add`)**
   - **Status:** **Behebung bestätigt.**
   - **Beweis:** In `bin/vibe-web.py:1790-1794` wird der Rückgabewert von `vibe.add_bug` bzw. `vibe.add_feedback` nun als `fid` entgegengenommen und mit `f"{fid} eingetragen"` formatiert (`"B1 eingetragen"` bzw. `"F1 eingetragen"`). Parallel hat der Test-Agent in `tests/unit/test_work_packages.py:428,471` und `tests/unit/test_feedback_capture.py:248` die früheren Substring-Prüfungen (`assertIn`) durch exakte Vergleiche (`assertEqual("B1 eingetragen", json.loads(body).get("message"))` bzw. `"F1 eingetragen"`) ersetzt.

2. **[Medium] `bin/vibe-web.py:2050-2058` — `TypeError` bei `POST /api/github` (`action="import"`) und `TICKETS.md`-Verweis**
   - **Status:** **Behebung bestätigt.**
   - **Beweis:** `bin/vibe-web.py:2050-2058` verarbeitet `(added: int, seen: int)` jetzt typgerecht ohne `", ".join(added)`:
     - `if added:` → `f"Issues übernommen ({added} von {seen} Issues)."`
     - `elif seen:` → `f"Keine neuen Issues ({seen} gesehen); Ticketspeicher unverändert."`
     - `else:` → `"Keine offenen Issues."`
     Damit ist der HTTP-500-Pfad beseitigt und der Wortlaut konsistent zu `cmd_github` in `bin/vibe:1061-1066`.

3. **[Medium] `docs/features/GH-48.md:187-355` — Migrationsschnipsel und `## Grenzen`**
   - **Status:** **Behebung bestätigt.**
   - **Beweis:**
     - `FIELD_RE` (`docs/features/GH-48.md:210`) erkennt jetzt auch `Priorität` und `Abhängigkeiten` (mit Validierung über `DEP_RE` in Zeilen 211, 264–270 und Übergabe an `vibe_tickets.add` in Zeilen 324–325).
     - `parse()` (`docs/features/GH-48.md:214-281`) merkt sich das aktive Feld in `current = key` und hängt eingerückte Folgezeilen bei `current == "Beschreibung"` sauber mit `"\n"` an `record["description"]` an (Zeilen 275–280).
     - Eine Zeile `GitHub: Issue #<n> auf GitHub geschlossen` setzt über `if "geschlossen" in value and not record.get("test"):` das `test`-Feld auf `"GitHub-Issue #%d geschlossen" % number` (Zeilen 248–249).
     - Die Done-Degradierung (`docs/features/GH-48.md:292-295`) prüft `not (record.get("test") and (record.get("commit") or record.get("github")))` und ist damit deckungsgleich zur Done-Invariante in `bin/vibe_tickets.py:185-192`.
     - Der Ausführungshinweis für `sys.path.insert` (`docs/features/GH-48.md:201-203,333-335`) und der Abschnitt `## Grenzen` (`docs/features/GH-48.md:344-347`, Bestandsmigration als abgeschlossen dokumentiert) sind aktualisiert.

4. **[Minor] `bin/vibe_packages.py:507-568,1279` — Entfernung von `_type_rank` und Docstring-Korrektur in `select_package`**
   - **Status:** **Behebung bestätigt (inkl. ausdrücklicher Bestätigung der Docstring-Korrektur).**
   - **Beweis:** `_type_rank` ist aus `bin/vibe_packages.py` entfernt; sowohl `select_package` (`bin/vibe_packages.py:565`: `key = (priority(record), index)`) als auch `priority_view` (`bin/vibe_packages.py:1279`: `((priority(record), index), record)`) sortieren strikt nach `(priority, Position im Speicher)`. Die vom Coder transparent gemeldete Anpassung des Docstrings von `select_package` (`bin/vibe_packages.py:516-518`: „sortiert wird nach Priorität (P0..P8, ohne Angabe hinten) und dann nach der Position im Ticketspeicher") gibt den Implementierungsvertrag (§4) und `docs/features/GH-48.md:83-84` exakt wieder. Der Vertragstest `test_standard_order_is_priority_then_store_position` (`tests/unit/test_gh48_runner_tickets.py:217-238`) prüft nun konsistent `["AP2", "AP1", "B1", "AP3"]`.

5. **[Minor] `bin/vibe:24`, `bin/web/app.js:355,1108`, `bin/web/i18n.js:104,312,1228,1436` — Rest-Hinweistexte & `docs/import-manifest.json`**
   - **Status:** **Behebung bestätigt.**
   - **Beweis:** Ein `grep` über `bin/` nach `TICKETS\.md|FEEDBACK\.md` findet nur noch drei historische Erklärkommentare (`bin/vibe_tickets.py:5`, `bin/vibe:525`, `bin/vibe_packages.py:90`) und keinen einzigen produktiven Code- oder UI-String mehr. `bin/vibe:24` lautet jetzt `vibe feedback <p>    neues Feedback-Ticket im Ticketspeicher anlegen`; `bin/web/app.js:355,1108` und beide Sprachblöcke (`en`/`de`) in `bin/web/i18n.js:104,312,1228,1436` sind schlüssig aktualisiert. `docs/import-manifest.json` enthält die neuen Grössen und SHA-256-Prüfsummen für `bin/vibe`, `bin/vibe-web.py`, `bin/vibe_packages.py`, `bin/web/app.js` und `bin/web/i18n.js`.

6. **[Minor] `docs/features/F15-arbeitspakete.png`, `docs/features/F9-assistent.png` — Aktualisierte Screenshots**
   - **Status:** **Behebung bestätigt.**
   - **Beweis:** In `docs/features/GH-48.md:130-135` sind beide durch die echten Browser-Abnahmeläufe aktualisierten Screenshots ausdrücklich als gewollte Nachweisaktualisierung dokumentiert.

## 3. Abgleich Ticket ↔ Umsetzung (Acceptance Criteria)

| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| **1. Einheitliches System statt getrennter `TICKETS.md` und `FEEDBACK.md`** (Arbeitspakete, Bugs, Feedback in einem Speicher mit `type`-Feld) | PASS | `bin/vibe_tickets.py:28-32,142-145,256-298`; `bin/vibe:528-616` | `tests/unit/test_gh48_ticket_store.py`, `tests/unit/test_gh48_tickets_surface.py` (Rot→Grün in `docs/reviews/GH-48-test-agent-report.md` §§3, 9, 10). |
| **2. Maschinenlesbares JSON-Format ohne Ticket-Parsing-Regexes im Produktcode** | PASS | `bin/vibe_tickets.py:68-113`; Altparser aus `bin/vibe`, `bin/vibe_packages.py`, `bin/vibe_issues.py`, `bin/vibe_github.py` entfernt | Grep über `bin/` bestätigt vollständige Entfernung aller Markdown-Blockparser. |
| **3. Distinkte Felder** (`id`, `title`, `type`, `state`, `description`, `github`, `pr_url`, `commit`, `test`, `blocked_reason`, `waiting_note`, `priority`, `dependencies`, `created`, `updated`) inkl. Done-Invariante & Vorwärtskompatibilität | PASS | `bin/vibe_tickets.py:115-195,256-330`; `bin/vibe_packages.py:1079-1093`; `bin/vibe-run.sh:1445` | `tests/unit/test_gh48_ticket_store.py:158-303`. |
| **4. Ablage in `.vibe/tickets.json` & atomare Konfliktbehandlung** | PASS | `bin/vibe_tickets.py:31,61-63,95-113,224-240` | `vibe_storage.write_text(..., expected=...)` + `TicketStoreConflict`; `tests/unit/test_gh48_ticket_store.py:138-157`. |
| **5. Default-`.gitignore` mit `.vibe/` für neue Projekte** (`cmd_new` vor `_init_git`, idempotent in `cmd_init`/Adopt, Symlink-Schutz, `.vibe/` in `ensure_project_exclude`) | PASS | `bin/vibe:2390-2419,2716-2723,2762,2943-2946`; `bin/vibe_packages.py:612` | `tests/unit/test_gh48_scaffold_templates.py:99-202`. |
| **6. Neue Workflow-Anweisungen für `AGENTS.md` (kopierfertig in Doku) + Vorlagen & `GENERAL_RULES` identisch angepasst** | PASS | `bin/vibe:119-136`; `templates/{generic,android,web,docker,rebuild}/AGENTS.md`; `docs/features/GH-48.md:137-185`; `scripts/setup-vibe.py:60`; `bin/vibe_guide.py:118-124,241-264` | `templates/common/TICKETS.md` & `FEEDBACK.md` gelöscht; `tests/unit/test_gh48_scaffold_templates.py:204-288`, `tests/unit/test_setup_vibe.py`. |
| **7. `SPEC.md` und `docs/grenzen.md` minimal an fehlerhaften Stellen angepasst** | PASS | `SPEC.md:74-81,293`; `docs/grenzen.md:7` | Durch `git diff ad00c0b -- SPEC.md docs/grenzen.md` verifiziert. |
| **8. Transport nur des aktuellen Tickets als sichtbare Einzeldatei `TICKET-<ID>.json` in den Feature-Worktree** (Exclude über `rev-parse --git-path info/exclude`, Gate & `sync-ticket`) | PASS | `bin/vibe_packages.py:164-171,225-244,279-325,507-586,1097-1162,1369-1412`; `bin/vibe-run.sh:513-517,885,904,1476,1604,1616-1621` | `tests/unit/test_gh48_runner_tickets.py` (29/29 OK), `tests/unit/test_worknotes_sync.py` (16/16 OK). |
| **9. Local-only + GitHub-Support sowie Offline-Zustände in Backend & UI** | PASS | `bin/vibe_issues.py:174-348`; `bin/vibe_github.py:1199-1219,1730-1765`; `bin/vibe-web.py:94-124,1781-1860,2050-2058`; `bin/web/app.js:355,685-703,1108`; `bin/web/i18n.js:104,312,1228,1436`; `bin/web/nova-project.js:104-110,211-234,321-381` | `tests/unit/test_gh48_web_api.py`, `tests/unit/test_gh48_tickets_surface.py`, `tests/unit/test_work_packages.py`, `tests/unit/test_feedback_capture.py`, `tests/browser/test_gh48_tickets_ui.py`. |
| **10. Keine Migration im Produktcode; funktionsfähiger Migrationsschnipsel in `docs/features/GH-48.md` (ohne Tests)** | PASS | `docs/features/GH-48.md:187-340` | Logik für mehrzeilige Beschreibungen, `Commit: ...; Test: ...`, `GitHub: Issue #n ... geschlossen`, `Priorität`/`Abhängigkeiten`, `GH-`-Speicherpfad und Done-Degradierung lesend geprüft. |

## Findings
- No findings.

## Verification
- Change set reviewed: `ad00c0b..working tree` (51 geänderte getrackte Dateien, 2 gelöschte Dateien, 10 ungetrackte neue Dateien inkl. `docs/reviews/GH-48-review-1.md`).
- Git commands run by me: `git status --short`, `git diff ad00c0b -- bin/vibe-web.py bin/vibe bin/vibe_packages.py bin/web/app.js bin/web/i18n.js docs/import-manifest.json`, `git diff ad00c0b -- tests/unit/test_gh48_runner_tickets.py tests/unit/test_work_packages.py tests/unit/test_feedback_capture.py`.
- Checks evidenced by supplied raw output: keine Rohausgaben direkt im Prompt, detaillierte Testläufe in `docs/reviews/GH-48-test-agent-report.md` §§3, 8, 9, 10 dokumentiert.
- Checks reported only by the coding agent: `python3 -m unittest` Abschlussbatterie 10 Module (Ran 243 OK), `tests.browser.test_gh48_tickets_ui` (Ran 3 OK), `test_work_packages + test_feedback_capture` (Ran 35 OK), `test_gh48_runner_tickets` (Ran 29 OK), `bash scripts/verify.sh quick` (Exit 0), `python3 scripts/check-import-manifest.py` (OK 71 Dateien).
- Checks not independently run: alle Build-, Test- und sonstigen Nicht-Git-Befehle (gemäß System-Rollenvorgabe für den strikt lesenden Review-Agenten).
- Important areas inspected: `bin/vibe-web.py`, `bin/vibe`, `bin/vibe_packages.py`, `bin/vibe_tickets.py`, `bin/web/app.js`, `bin/web/i18n.js`, `docs/features/GH-48.md`, `docs/import-manifest.json`, `docs/reviews/GH-48-test-agent-report.md`, `tests/unit/test_gh48_runner_tickets.py`, `tests/unit/test_work_packages.py`, `tests/unit/test_feedback_capture.py`.
- Remaining risks: Der einmalige Abnahme-Volllauf (`bash scripts/verify.sh full`) vor dem Paketabschluss steht planmäßig als nächster Schritt nach diesem Review an.

Verdict: PASS
