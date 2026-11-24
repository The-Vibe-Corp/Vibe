# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

### Kurzurteil
Der Änderungssatz für Ticket **B1** (`TICKET-B1.json`, Ausgangscommit `821982c`, Branch `feature/korbat/b1`) setzt alle vier Anforderungen aus Ticket, verbindlichen Nutzerentscheidungen und `SPEC.md` sauber, minimal-invasiv (KISS/Clean Code) und abwärtskompatibel um. Die Testsuite (`tests/browser/test_b1_work_ui.py` sowie die gezielten Vertragsanpassungen in den bestehenden Testmodulen) ist nachweislich unabhängig aus Ticket und Spezifikation abgeleitet, vollständig dokumentiert (Vorbedingung/Aktion/Erwartung) und frei von Abschwächungen unbeteiligter Assertions. Da meine Agentenrolle strikt schreibgeschützt ist und nur read-only Git-Befehle erlaubt (`Permission denied: shell` bei Test-/Build-Kommandos), wurden die Testläufe anhand des statischen Diffs und der mitgelieferten Prüfprotokolle bewertet und die Einschränkung transparent ausgewiesen. Ein nicht-blockierender Hinweis (`Minor`) betrifft die geplante Dokumentations-Namenskonvention für `gate_errors`.

---

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| **1. Anlageformular:** Genau EIN Typfeld (`feature`/`bug`/`feedback`) statt doppelter Kategorie/Tickettyp; „Paket" (`task`) entfällt als Wahl (`task` bleibt speicher-/API-kompatibel); ungenutzter i18n-Key `"Kategorie"` entfernt | PASS | `bin/web/nova-project.js:893-906, 927, 2396-2407`, `bin/web/i18n.js:1020-1025, 2142-2147`, `bin/vibe_tickets.py:29-30` | `tests/browser/test_b1_work_ui.py:321-380` (`test_01_single_ticket_type_field_replaces_category`, `test_02_buttons_preselect_the_type`), `tests/browser/test_gh67_work_ui.py:956-1035, 1195-1272`, `tests/unit/test_ap3_korbat_surfaces.py:855-875` (mitgelieferte Testausgabe: 69 Browser-Tests OK) |
| **2. Ruhiger Editor (Option A):** Editor (Öffnen/Speichern/Abbrechen) ändert NIE den Zustand (`nvpStartTicketProgress` und `editState` entfernt); manuelle Wechsel (Detail-Zustandsauswahl `draft`/`open`/`in-progress`, Board-Buttons, DnD) bleiben vollständig | PASS | `bin/web/nova-project.js:875-997` (Entfernung von `nvpStartTicketProgress`, `editState` und Auto-Trigger beim Öffnen) | `tests/browser/test_b1_work_ui.py:383-429, 515-545` (`test_03_editor_open_cancel_and_save_keep_the_state`, `test_06_manual_state_change_draft_to_open_still_works`), `tests/browser/test_gh67_work_ui.py:1275-1454` (`test_33`..`test_38`), `tests/browser/test_gh56_work_ui.py:765-800` (mitgelieferte Testausgabe: 69 Browser-Tests OK) |
| **3. Einheitliche Anlage über `/api/ticket` (`action=add`):** Nova-UI schickt `add` für alle Typen an `/api/ticket` mit `type` und `state=draft`; verbundene Projekte legen zuerst GitHub-Issue an (Labels aus `type` für `bug`/`feature`/`feedback`, `task` ohne Typ-Label; Ready-Label nur bei `open`; `GH-<n>` mit `type`/`state`/`github`); Offline-Auto-ID `feature`→`AP<n>` (gemeinsamer Zähler mit `task`), `bug`→`B<n>`, `feedback`→`F<n>`; unbekannter Typ abgelehnt; Default `feature` | PASS | `bin/web/nova-project.js:947-961`, `bin/vibe-web.py:1833-1860`, `bin/vibe_issues.py:460-492`, `bin/vibe_tickets.py:30` | `tests/browser/test_b1_work_ui.py:431-513` (`test_04`, `test_05`), `tests/unit/test_gh48_ticket_store.py:308-330`, `tests/unit/test_gh48_web_api.py:241-296, 393-498`, `tests/unit/test_ap3_korbat_issues_backend.py:954-1018`, `tests/unit/test_ap3_korbat_surfaces.py:371-485` (mitgelieferte Testausgabe: 115 Unit-Tests OK, 69 Browser-Tests OK) |
| **4. Läufer `mark_start` / CLI `mark-start`:** Setzt `open`→`in-progress` idempotent (`in-progress`→`False`, andere Zustände/fehlend→`False`); verbundene Tickets erhalten In-Progress-Label via `vibe_issues.set_issue_state` (REST-Fehler → lokal trotzdem `in-progress`, Best-effort-Meldung); `bin/vibe-run.sh` ruft `mark-start` nach `worktree-register` und vor `copy-notes` mit `\|\| true` (nicht blockierend) auf | PASS | `bin/vibe_packages.py:52-64, 1117-1153, 1556-1565, 1795-1802`, `bin/vibe-run.sh:1591-1593` | `tests/unit/test_gh48_runner_tickets.py:598-850` (`MarkStartedTest`, 11 Testfälle inkl. Loopback-GitHub-Fake, REST-500-Fallback, Transport-Reihenfolge vor `copy-notes`, `vibe-run.sh`-Reihenfolge & `\|\| true`) (mitgelieferte Testausgabe: 115 Unit-Tests OK) |

---

## Spezifische Prüfpunkte & Detailanalyse

1. **Vertragstreue gegen `SPEC.md` (Critical/High/Major: 0 — PASS):**
   - `SPEC.md:74-82` („Arbeitspakete und Feedback“): Tickets (`task`, `feature`, `bug`, `feedback`) liegen einheitlich in `.vibe/tickets.json`; die Zustände (`draft`, `open`, `in-progress`, `blocked`, `waiting-merge`, `done`) gelten mit und ohne GitHub-Verbindung; IDs werden bei leerem Feld automatisch und kollisionsfrei vergeben (`feature` und `task` teilen sich den `AP<n>`-Zähler in `bin/vibe_tickets.py:30, 214-223`); eine eigene ID bleibt möglich (`bin/vibe-web.py:1857`, `bin/vibe_tickets.py:271-279`).
   - Done-Invariante (`SPEC.md:79-80`, `bin/vibe_tickets.py:186-194`) und `gate_errors` (`bin/vibe_packages.py:1161-1241`) sind unberührt und streng.

2. **Test-Stamm und ausdrückliche Bestätigung der Test-Unabhängigkeit (PASS):**
   - **Bestätigt:** Alle neuen Tests in `tests/browser/test_b1_work_ui.py` (7 Browser-Tests) und `tests/unit/test_gh48_runner_tickets.py` (`MarkStartedTest`, 11 Unit-Tests) sowie die erweiterten Tests in `test_gh48_web_api.py`, `test_gh48_ticket_store.py`, `test_ap3_korbat_issues_backend.py` und `test_ap3_korbat_surfaces.py` besitzen vollständige Docstrings mit **Vorbedingung (`Vor:`)**, **Aktion (`Aktion:`)** und **Erwartung (`Erwartung:`/`Erwartet:`)** (teils ergänzt um `Significance:`/`Fehlerfall:`). Sie prüfen beobachtbare Verträge (DOM-Selektoren, HTTP-Payloads, Store-Zustand, Loopback-REST-Calls, CLI-Exitcodes) und sind unabhängig aus Ticket B1 und `SPEC.md` abgeleitet.
   - **Keine Abschwächung bestehender Tests:** Der vollständige Diff von `tests/` gegen `821982c` wurde Zeile für Zeile geprüft. In `test_gh67_work_ui.py` wurden ausschließlich die durch B1 abgelösten Verträge (`category`-Select in `test_21`..`test_23`, `test_30`..`test_32` sowie der automatische `in-progress`-Wechsel beim Öffnen des Editors in `test_33`..`test_38`) auf den neuen B1-Vertrag umgestellt. Alle Tests für Board-Buttons („Freigeben"/„Zurück in Planung"), Drag-and-Drop, Detail-Zustandsauswahl, Statusmapping/Badges, Done-Schutz und Token-Pflicht sind **unverändert** erhalten.
   - **Stale-Marker `issuesEnabled` & 5 vorbestehende Failures in `test_ap3_korbat_surfaces.py`:** In `tests/unit/test_ap3_korbat_surfaces.py:855-875` wurde die Entfernung der am Branchpunkt bereits unerfüllbaren Assertion `js_region(self.text, "var issuesEnabled = !!(data.github")` im Docstring transparent begründet. Die 5 vorbestehenden Failures in `test_ap3_korbat_surfaces.py` wurden nicht maskiert und es kamen keine neuen hinzu.

3. **`/api/feedback` (Legacy) vs. Nova-UI (PASS):**
   - `bin/vibe-web.py:1789-1828` zeigt im Diff gegen `821982c` keinerlei Änderung an `/api/feedback`.
   - In `bin/web/nova-project.js:948-961` nutzt `nvpOpenTicketForm` `/api/feedback` nur noch beim Bearbeiten (`editing && (mode === 'bug' || mode === 'feedback')`). Jede Neuanlage (`!editing`) geht für alle Typen (`feature`, `bug`, `feedback`) über `POST /api/ticket` mit `action: 'add'`, `type: selectedType`, `state: 'draft'`. `test_04_creation_is_sent_to_the_ticket_api_with_type_and_draft` (`tests/browser/test_b1_work_ui.py:431-478`) fängt sowohl `/api/ticket` als auch `/api/feedback` ab und verifiziert `feedback_adds == []`.

4. **Sicherheit & Validierung (PASS):**
   - Keine Tokens oder Geheimnisse in Fehlermeldungen oder Logs (`mark_start` gibt bei `GitHubError` einen statischen Hinweis ohne Exception-Details oder Header aus: `bin/vibe_packages.py:1144-1148`).
   - Alle GitHub-REST-Aufrufe laufen ausschließlich über die bestehenden Helper in `vibe_issues.py` (`create_issue`, `set_issue_state` → `vibe_github`).
   - `vibe_tickets.normalize` (`bin/vibe_tickets.py:115-195`) ist unverändert streng. Sowohl `/api/ticket` (`bin/vibe-web.py:1844-1848`) als auch `add_ticket_connected` (`bin/vibe_issues.py:474-475`) lehnen unbekannte Tickettypen vor jedem REST- oder Schreibversuch mit `ValueError` ab.

5. **KISS / Clean Code (PASS):**
   - Ein grep über `bin/` bestätigt: `nvpStartTicketProgress`, `editState` und `categorySelect` sind restlos aus `bin/web/nova-project.js` entfernt.
   - Der entfernte i18n-Schlüssel `"Kategorie"` in `bin/web/i18n.js` hat in `bin/web/` null Referenzen (das Wort kommt nur noch in einem Python-CLI-Print in `bin/vibe_mcp.py:1188` und in deutschen Kommentaren vor).
   - `docs/import-manifest.json` aktualisiert die Größen und SHA-256-Prüfsummen der 7 geänderten `bin/`-Dateien und begründet die Änderung im `aenderungen`-Eintrag für `B1` (`docs/import-manifest.json:1530-1544`).

6. **Läufer-Sicherheit & Fehlerverhalten von `mark_start` (PASS / Note):**
   - `mark-start` wird in `bin/vibe-run.sh:1593` nach `worktree-register` (Zeile 1587) und vor `copy-notes` (Zeile 1606) mit `>>"$LOG" 2>&1 || true` aufgerufen.
   - Beim ersten Start eines `open`-Tickets wechselt der Zustand in `.vibe/tickets.json` auf `in-progress`, sodass `copy-notes` unmittelbar danach `state: "in-progress"` in `$WT/TICKET-<ID>.json` transportiert (`test_transport_after_mark_start_carries_in_progress`).
   - Bei `RECONNECT=1` ist das Ticket bereits `in-progress`; `mark_start` erkennt `record.get("state") == "in-progress"`, lässt den Speicher bytegleich (`changed=False`), `command_mark_start` gibt `HINWEIS: Ticket <ID> ist bereits in Bearbeitung.` mit Exitcode `1` (`EXIT_NONE`) aus, und `|| true` in `vibe-run.sh` verhindert jede Unterbrechung des Laufs.
   - Fehlt in einer Teilinstallation `vibe_github.py` oder `vibe_issues.py`, wirft `_github_module()` bzw. `_issues_module()` exakt wie die bestehenden Helper in `bin/vibe_packages.py:35-64` einen kontrollierten `SystemExit` mit klarer Meldung, der im Läufer ins Log geschrieben und über `|| true` nicht-blockierend abgefangen wird. Das ist konsistent zur bestehenden Architektur von `vibe_packages.py` und kein Befund.

7. **Abwärtskompatibilität (PASS):**
   - `TYPES = ("task", "bug", "feature", "feedback")` (`bin/vibe_tickets.py:29`) behält `task`. Bestandstickets mit `type="task"`, `state="done"` oder `GH-<n>`-IDs laden und normalisieren unverändert.
   - `add_ticket_connected` (`bin/vibe_issues.py:474-491`) akzeptiert weiterhin `ttype="task"` ohne GitHub-Typ-Label (`test_connected_add_accepts_task_without_a_type_label`).
   - `select_package` (`bin/vibe_packages.py:554-561`) wählt weiterhin Kandidaten mit `state in ("open", "in-progress")`, sodass vom Läufer auf `in-progress` gesetzte Tickets bei Folgedurchgängen oder Reconnects regulär ausgewählt bleiben.

---

## Findings

- [Minor] `bin/vibe_packages.py:1220` — Namenskollision `docs/features/B1.md` bei der Abschlussschranke (`gate_errors`) beachten
  - Evidence: Der Koordinator plant wegen des historischen Eintrags in `docs/features/B1.md` die neue Feature-Dokumentation unter `docs/features/B1-ticketlogik.md` anzulegen. `gate_errors` in `bin/vibe_packages.py:1220-1222` prüft beim Paketabschluss jedoch zwingend auf die Existenz von `project / "docs" / "features" / (pid + ".md")` (`docs/features/B1.md`). Zudem wurde beim früheren Namenskollisionsfall B1 (`2026-11-20`, siehe `docs/features/B1.md:258` und `docs/reviews/B1-review-3.md:40`) der neue B1-Abschnitt an `docs/features/B1.md` angehängt (und bei B7 existieren sowohl `docs/features/B7.md` als auch `docs/features/B7-subagent-permissions.md`). Die Zählung der Review-Datei ab `docs/reviews/B1-review-4.md` ist hingegen exakt kompatibel mit `review_order` (`bin/vibe_packages.py:1155-1158, 1227-1231`), da `paths[-1]` die höchste Nummer (`4 > 3`) auswählt.
  - Required fix: Beim Erstellen der Dokumentation vor dem Commit sicherstellen, dass `docs/features/B1.md` den aktuellen B1-Abschnitt enthält (entweder als neuer abgegrenzter Abschnitt in `docs/features/B1.md` wie in Runde B1-2026-11-20 oder zusätzlich zu `docs/features/B1-ticketlogik.md` mit Querverweis), damit sowohl die Historie als auch `gate_errors` (`docs/features/B1.md`) erfüllt sind.

---

## Verification
- Change set reviewed: `821982c..working tree` auf Branch `feature/korbat/b1` (15 geänderte Dateien, 1 neue Testdatei `tests/browser/test_b1_work_ui.py`).
- Git commands run by me:
  - `git status --short`
  - `git diff --stat 821982c`
  - `git diff 821982c -- bin/`
  - `git diff 821982c -- tests/`
  - `git diff 821982c -- docs/import-manifest.json`
- Checks evidenced by supplied raw output:
  - `python3 -m unittest tests.unit.test_gh48_ticket_store tests.unit.test_gh48_web_api tests.unit.test_ap3_korbat_issues_backend tests.unit.test_gh48_runner_tickets` → `Ran 115, OK`
  - `python3 -m unittest tests.unit.test_ap3_korbat_surfaces` → `Ran 25, FAILED (failures=5)` (exakt die 5 vorbestehenden Failures)
  - `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_b1_work_ui tests.browser.test_gh67_work_ui tests.browser.test_gh56_work_ui` → `Ran 69 (7+41+21), OK`
  - `bash scripts/verify.sh quick` → `Exit 0`
  - `bash scripts/verify.sh package` → `Exit 0`
  - `node --check bin/web/nova-project.js` → `OK`
- Checks reported only by the coding agent: siehe oben (Ergebnisse wurden im Task-Prompt übergeben; eigene Shell-Testausführung ist durch die Reviewer-Tool-Policy `Permission denied: shell` für Nicht-Git-Befehle gesperrt).
- Checks not independently run: all build, test, and other non-Git checks (`python3 -m unittest ...`, `node --check ...`, `bash scripts/verify.sh ...`).
- Important areas inspected:
  - `bin/vibe_tickets.py`, `bin/vibe_issues.py`, `bin/vibe-web.py`, `bin/vibe_packages.py`, `bin/vibe-run.sh`, `bin/web/nova-project.js`, `bin/web/i18n.js`
  - `tests/browser/test_b1_work_ui.py`, `tests/browser/test_gh67_work_ui.py`, `tests/browser/test_gh56_work_ui.py`
  - `tests/unit/test_gh48_runner_tickets.py`, `tests/unit/test_gh48_ticket_store.py`, `tests/unit/test_gh48_web_api.py`, `tests/unit/test_ap3_korbat_issues_backend.py`, `tests/unit/test_ap3_korbat_surfaces.py`
  - `docs/import-manifest.json`, `docs/features/B1.md`, `docs/reviews/B1-review-3.md`
- Remaining risks:
  - Vor dem Paketabschluss stehen noch der einmalige Abnahmelauf `bash scripts/verify.sh full` durch den Koordinator sowie das Anlegen der Feature-Dokumentation und das Speichern dieses Review-Berichts unter `docs/reviews/B1-review-4.md` aus.

Verdict: PASS
