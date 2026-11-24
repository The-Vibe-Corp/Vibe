# Review GH-48 — Runde 1 (unabhängiger Review-Agent)

Arbeitspaket: GH-48 „Improve ticket system" (GitHub #48)
Repository: /var/log/custom/vibe-dev/worktrees/vibe-GH-48-7su7Ui, Branch feature/korbat/gh-48
Startcommit: ad00c0b
Änderungssatz: 50 geänderte getrackte Dateien, 2 gelöschte Dateien (templates/common/TICKETS.md, FEEDBACK.md), 9 neue Dateien (bin/vibe_tickets.py, docs/features/GH-48.md, docs/reviews/GH-48-test-agent-report.md, tests/unit/test_gh48_*.py [5 Module], tests/browser/test_gh48_tickets_ui.py)
Rollen: strikt lesender Review; keine Dateiänderungen, keine Builds/Tests eigenständig ausgeführt (nur lesende Git-Befehle).

## 1. Zusammenfassung des Änderungssatzes

Der Änderungssatz für **GH-48 „Improve ticket system"** (Startcommit `ad00c0b..working tree`, 50 geänderte getrackte Dateien, 2 gelöschte Dateien, 9 neue Dateien) überführt die bisher getrennten Markdown-Ledger `TICKETS.md` und `FEEDBACK.md` in den einheitlichen, maschinenlesbaren und unversionierten Ticketspeicher `.vibe/tickets.json` (`bin/vibe_tickets.py`). Alle Oberflächen (`bin/vibe`, `bin/vibe-web.py`, `bin/web/app.js`, `bin/web/nova-project.js`), die GitHub-Synchronisation (`bin/vibe_issues.py`, `bin/vibe_github.py`), der Projektassistent (`bin/vibe_guide.py`), das Gerüst samt `.gitignore`-Absicherung und die fünf `AGENTS.md`-Vorlagen wurden auf das feldbasierte Format umgestellt, und der Runner (`bin/vibe_packages.py`, `bin/vibe-run.sh`) transportiert nur noch das aktuelle Ticket als sichtbare Datei `TICKET-<ID>.json` in die Arbeitskopie. Während der Kern (`bin/vibe_tickets.py`), die Runner-Schranken und die 6 neuen sowie 26 migrierten Testmodule von solider Qualität sind, besteht ein funktionaler Mangel (High) bei der Web-API für Bug-/Feedback-Meldungen (`FB1`/`FF1`-Doppelpräfix) sowie zwei mittlere Mängel (Medium) im Web-Import-Handler (`TypeError` bei `added > 0`) und in der Fachdokumentation `docs/features/GH-48.md` (einzeiliger `parse()`-Schnipsel verschluckt mehrzeilige Beschreibungen).

## Summary
- Critical: 0
- High: 1
- Medium: 2
- Minor: 3
- Verdict: CHANGES REQUIRED

## 2. Fundstellen (klassifiziert)

- [High] `bin/vibe-web.py:1790` — Doppeltes Präfix (`FB1` / `FF1`) in den Rückmeldungen von `POST /api/feedback` (`action=add`) und irreführender Variablenname `num`
  - Evidence: In `bin/vibe:370-387` geben `add_feedback` und `add_bug` seit GH-48 nicht mehr die bloße Integer-Nummer (früher `_add_entry(...) -> int`), sondern die vollständige Ticket-ID `record["id"]` (also `"F1"`, `"B1"`, …) zurück; `cmd_feedback` in `bin/vibe:2354` wurde entsprechend von `f"F{n} eingetragen"` auf `f"{n} eingetragen"` angepasst. In `bin/vibe-web.py:1790-1794` steht jedoch weiterhin:
    ```python
    num = vibe.add_bug(name, t, body.get("description", ""), state=state)
    ok, msg = True, f"B{num} eingetragen"
    else:
    num = vibe.add_feedback(name, t, body.get("description", ""), state=state)
    ok, msg = True, f"F{num} eingetragen"
    ```
    Dadurch lautet die API-Antwort und der UI-Toast `"BB1 eingetragen"` bzw. `"FF1 eingetragen"`. Bestehende Substring-Assertions wie `self.assertIn("B1 eingetragen", body)` (`tests/unit/test_work_packages.py:477`) und `self.assertIn("F1 eingetragen", body)` (`tests/unit/test_feedback_capture.py:247`) bemerken den Fehler nicht, weil `"F1 eingetragen"` ein Teilstring von `"FF1 eingetragen"` ist.
  - Required fix: In `bin/vibe-web.py:1790-1794` den Rückgabewert als `fid` behandeln und `f"{fid} eingetragen"` formatieren, damit die Meldung exakt `"B1 eingetragen"` bzw. `"F1 eingetragen"` lautet.

- [Medium] `bin/vibe-web.py:2050` — `POST /api/github` mit `action="import"` wirft `TypeError` bei `added > 0` und nennt bei `added == 0` noch `TICKETS.md`
  - Evidence: `vibe.github_issues_import` (`bin/vibe:905`) gibt seit GH-48 `(added: int, seen: int)` zurück, weil `vibe_github.import_issues_into_tickets` (`bin/vibe_github.py:1765`) die Anzahl `added` als `int` statt einer ID-Liste liefert. In `bin/vibe:1061-1066` (`cmd_github`) wurde die Formatierung auf `% (added, seen)` und `"Ticketspeicher unverändert."` angepasst. In `bin/vibe-web.py:2050-2055` steht dagegen noch der alte Code:
    ```python
    added, seen = vibe.github_issues_import(...)
    ok = bool(added) or seen == 0
    if not added and seen:
        msg = f"Keine neuen Issues ({seen} gesehen); TICKETS.md unverändert."
    else:
        msg = ("Arbeitspakete übernommen: " + ", ".join(added)) if added else "Keine offenen Issues."
    ```
    Sobald mindestens ein Issue importiert wird (`added >= 1`), schlägt `", ".join(added)` mit `TypeError: can only join an iterable` fehl (in `do_POST` nicht von `except ValueError:` gefangen → HTTP 500). Bei `added == 0` und `seen > 0` nennt die Meldung zudem noch `TICKETS.md unverändert.` statt `Ticketspeicher unverändert.`.
  - Required fix: In `bin/vibe-web.py:2052-2055` die Meldungen analog zu `bin/vibe:1061-1066` auf die Integer-Rückgabe und den Ticketspeicher umstellen (z. B. `f"Issues übernommen ({added} von {seen} Issues)."` und `f"Keine neuen Issues ({seen} gesehen); Ticketspeicher unverändert."`).

- [Medium] `docs/features/GH-48.md:205` — Migrationsschnipsel verliert mehrzeilige Beschreibungen, mehrzeilige/separate Testnachweise und Prioritäten/Abhängigkeiten und verengt die Done-Invariante
  - Evidence: Im dokumentierten Migrationsschnipsel (`docs/features/GH-48.md:187-296`) wurden zwar das Einzeilen-Muster `Commit: <hash>; Test: …` (Zeilen 234–243), der `GH-`-Speicherpfad mit `read_snapshot`/`expected` (Zeilen 267–283) und die Degradierung unvollständiger `done`-Tickets (Zeilen 260–262) berücksichtigt, aber:
    1. `parse()` (Zeilen 205–250) prüft jede Zeile nur mit `FIELD_RE` (`^\s{2,}(Art|Status|...):\s*(.*)$`). Alle eingerückten Folgezeilen einer mehrzeiligen `Beschreibung:` (wie in `TICKETS.md:9-104`, `109-116`, `120-123`, `127-150`, `239-243`) matchen `FIELD_RE` nicht und werden durch `if not field: continue` komplett verworfen; bei Tickets, deren `Beschreibung:` nach einem Zeilenumbruch beginnt, bleibt `description` sogar leer `""`.
    2. In Zeile 261 prüft die Done-Degradierung `not (record.get("commit") and record.get("test"))`, während die echte Done-Invariante (`bin/vibe_tickets.py:185-192`) `has_test and (has_commit or has_github)` lautet und für auf GitHub geschlossene Issues (`GitHub: Issue #41 auf GitHub geschlossen`, vgl. `TICKETS.md:232`) auch `github` ohne `commit` zulässt.
    3. Zudem ist `sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin"))` (Zeile 195) fragil, wenn der Nutzer den Schnipsel nicht direkt im Repo-Stamm speichert, und `Priorität:`/`Abhängigkeiten:`-Zeilen sind in `FIELD_RE` nicht enthalten.
  - Required fix: Den Schnipsel in `docs/features/GH-48.md:187-296` so schärfen, dass eingerückte Folgezeilen nach `Beschreibung:` an `record["description"]` angehängt werden, `GitHub: Issue #<n> ... geschlossen` (bzw. `done` mit `github` ohne `commit`) das `test`-Feld setzt und die Done-Prüfung in Zeile 261 mit `bin/vibe_tickets.normalize` (`test` und (`commit` oder `github`)) übereinstimmt. Außerdem in `docs/features/GH-48.md:306-308` die veraltete Aussage unter `## Grenzen` („Bestandsmigration der Testmodule offen. Zahlreiche Alt-Testmodule prüfen noch das Markdown-Format und bleiben bis zu ihrer Überführung rot") aktualisieren, da laut Test-Bericht §8/§9 alle 26 Bestandsmodule bereits überführt und grün sind.

- [Minor] `bin/vibe_packages.py:378` — Undokumentierter Tiebreaker `_type_rank` in `select_package` weicht von Vertrag §4 und `docs/features/GH-48.md` §Runner-Ablauf ab
  - Evidence: Laut Vertrag §4 (`bin/vibe_packages.py:566-573`) und `docs/features/GH-48.md:83-84` lautet die Standardordnung `(priority, Position im Speicher)` und die alte Trennung `TICKETS`-vor-`FEEDBACK` entfällt. Tatsächlich sortiert `select_package` nach `(priority(record), _type_rank(record), index)`, wobei `_type_rank` `task`/`feature` (0) vor `bug`/`feedback` (1) bei gleicher Priorität bevorzugt. In `test_standard_order_is_priority_then_store_position` (`tests/unit/test_gh48_runner_tickets.py:217-237`) fällt dies nur deshalb auf `[AP2, AP1, AP3, B1]`, weil `_type_rank` `AP3` (ohne Prio, index 3) vor `B1` (ohne Prio, index 0) zieht — obwohl der Docstring des Tests ausdrücklich sagt: „die alte Trennung TICKETS vor FEEDBACK entfällt (nur Speicherposition zählt)".
  - Required fix: Entweder `_type_rank` in `docs/features/GH-48.md` explizit als gewollten Tiebreaker zwischen Priorität und Speicherposition dokumentieren oder (falls laut Vertrag nur `(priority, index)` gelten soll) `_type_rank` entfernen und den Testfall entsprechend ausrichten.

- [Minor] `bin/vibe:24` — Veraltete Verweise auf `TICKETS.md` und `FEEDBACK.md` in CLI-Hilfetext und klassischer UI (`bin/web/app.js:355,1108`)
  - Evidence:
    1. `bin/vibe:24`: Der CLI-Hilfetext lautet noch `vibe feedback <p>    neuen Punkt in FEEDBACK.md eintragen`.
    2. `bin/web/app.js:355` (und `bin/web/i18n.js:104,1228`): Der Hinweis in der Warnkarte `initCard` lautet noch `Ergänzt fehlende Dateien (FEEDBACK.md, TICKETS.md, AGENTS.md, .vibe/project.env)...`, obwohl `vibe init` keine `FEEDBACK.md`/`TICKETS.md` mehr anlegt.
    3. `bin/web/app.js:1108` (und `bin/web/i18n.js:312,1436`): Der Hinweistext in der GitHub-Karte lautet noch `Offene GitHub-Issues nach Label filtern und als Arbeitspakete (GH-Nummer) in TICKETS.md übernehmen.`.
  - Required fix: Hilfetext in `bin/vibe:24` sowie die beiden Hinweistexte in `bin/web/app.js` (samt Schlüssel in `bin/web/i18n.js`, falls dort übersetzt) auf den Ticketspeicher / `.gitignore` aktualisieren.

- [Minor] `docs/features/F15-arbeitspakete.png:1` — Zwei geänderte Bestands-Screenshots im Änderungssatz (`docs/features/F15-arbeitspakete.png`, `docs/features/F9-assistent.png`)
  - Evidence: Durch den echten Browser-Lauf von `tests/browser/test_tickets_ui.py` (`SHOT = SHOTS / "F15-arbeitspakete.png"`) und `tests/browser/test_project_guide_ui.py` (`SHOT = SHOTS / "F9-assistent.png"`) wurden die beiden getrackten PNG-Dateien im Arbeitsbaum aktualisiert. Inhaltlich spiegeln sie die neuen GH-48-Oberflächen wider (F15 zeigt das neue Feld „Zustand" im Ticket-/Bug-Formular; F9 zeigt den Assistenten ohne `TICKETS.md`/`FEEDBACK.md`), sie sind aber in `docs/features/GH-48.md` nicht als aktualisierte Nachweis-Screenshots erwähnt.
  - Required fix: Entweder die beiden aktualisierten Screenshots als gewollte UI-Nachweise in `docs/features/GH-48.md` benennen oder sie vor dem Commit auf `HEAD` zurücksetzen, falls keine Screenshot-Aktualisierung alter Feature-Nachweise beabsichtigt ist.

## 3. Abgleich Ticket ↔ Umsetzung (Acceptance Criteria)

| Anforderung (TICKETS.md `GH-48` & Vertrag) | Status | Beleg (Datei:Zeile) | Verifikation / Anmerkung |
|---|---|---|---|
| **1. Einheitliches System statt getrennter `TICKETS.md` und `FEEDBACK.md`** (Arbeitspakete, Bugs, Feedback als ein Ding mit `type`-Feld) | PASS | `bin/vibe_tickets.py:28-32,142-145,256-298`; `bin/vibe:528-616` | `tests/unit/test_gh48_ticket_store.py`, `tests/unit/test_gh48_tickets_surface.py` (vom Test-Agenten rot→grün dokumentiert). |
| **2. Maschinenlesbares JSON-Format ohne Ticket-Parsing-Regexes im Produktcode** | PASS | `bin/vibe_tickets.py:68-113`; alte Parser in `bin/vibe`, `bin/vibe_packages.py`, `bin/vibe_issues.py`, `bin/vibe_github.py` entfernt | Grep in `bin/` bestätigt: `_scan_blocks`, `_parse_entry`, `read_blocks`, `sync_proof`, `TICKET_GH_RE` etc. sind vollständig entfernt; nur Feld-Validierungsregexes (`_ID_RE`, `_COMMIT_RE`, `_PRIORITY_RE`) und `ensure_general_rules` (AGENTS.md) verbleiben. |
| **3. Distinkte Felder** (`id`, `title`, `type`, `state`, `description`, `github`, `pr_url`, `commit`, `test`, `blocked_reason`, `waiting_note`, `priority`, `dependencies`, `created`, `updated`) inkl. Done-Invariante & Vorwärtskompatibilität | PASS | `bin/vibe_tickets.py:115-195,256-330`; `bin/vibe_packages.py:1085-1099`; `bin/vibe-run.sh:1445` | `tests/unit/test_gh48_ticket_store.py:158-303` prüft Schema, Defaults, Invarianten und Erhalt unbekannter Schlüsser. |
| **4. Ablage im `.vibe`-Ordner (`.vibe/tickets.json`) & atomare Konfliktbehandlung** | PASS | `bin/vibe_tickets.py:31,61-63,95-113,224-240` | Nutzt `vibe_storage.write_text(..., expected=...)`; `ConcurrentChangeError` → `TicketStoreConflict(ValueError)`. |
| **5. Default-`.gitignore` mit `.vibe/` für jedes neue Projekt** (sowie idempotente Ergänzung in `init`/`adopt`, Symlink-Schutz, zusätzlich `.vibe/` in `ensure_project_exclude`) | PASS | `bin/vibe:2390-2419,2716-2723,2762,2943-2946`; `bin/vibe_packages.py:618` | `cmd_new` ruft `ensure_gitignore(p)` vor `_init_git(p)` auf (`bin/vibe:2762-2763`); `os.path.islink(path)` schützt vor Symlink-Writes (`bin/vibe:2400`). Getestet in `tests/unit/test_gh48_scaffold_templates.py:99-202`. |
| **6. Neue Workflow-Anweisungen für `AGENTS.md` (kopierfertig in Doku) + Vorlagen & `GENERAL_RULES` identisch angepasst** | PASS | `bin/vibe:119-136`; `templates/{generic,android,web,docker,rebuild}/AGENTS.md`; `docs/features/GH-48.md:131-178` | `templates/common/TICKETS.md` und `FEEDBACK.md` gelöscht; `vibe_guide.py:118-124,241-264` bereinigt; `setup-vibe.py:60` ergänzt. Getestet in `tests/unit/test_gh48_scaffold_templates.py:204-288`. |
| **7. `SPEC.md` (und `docs/grenzen.md`) minimal nur an fehlerhaften Stellen angepasst** | PASS | `SPEC.md:74-81,293`; `docs/grenzen.md:7` | `git diff ad00c0b -- SPEC.md docs/grenzen.md` geprüft: exakt die im Vertrag §§9–10 festgelegten Zeilen geändert. |
| **8. Transport nur des aktuellen Tickets als sichtbare Einzeldatei `TICKET-<ID>.json` in den Feature-Worktree** (inkl. Exclude über `git rev-parse --git-path info/exclude`, Gate & `sync-ticket`) | PASS | `bin/vibe_packages.py:164-171,225-244,279-325,1103-1168,1375-1418`; `bin/vibe-run.sh:513-517,885,904,1476,1604,1616-1621` | `shlex.quote` schützt `eval` in `bin/vibe-run.sh:513-517`. Getestet in `tests/unit/test_gh48_runner_tickets.py` und `tests/unit/test_worknotes_sync.py`. |
| **9. Local-only + GitHub-Support sowie Offline-Zustände in Backend & UI** | FAIL | `bin/vibe_issues.py:174-348`; `bin/vibe_github.py:1199-1219,1730-1765`; `bin/vibe-web.py:94-124,1781-1860,2050-2056`; `bin/web/app.js:685-703`; `bin/web/nova-project.js:104-110,211-234,321-381` | Zustandsauswahl (`draft`/`open`/`in-progress`, Default `open`), Wegfall von „ohne Nachweis" und `sync_issues` sind sauber umgesetzt, **aber** `bin/vibe-web.py:1790-1794` erzeugt `"BB1 eingetragen"`/`"FF1 eingetragen"` (High) und `bin/vibe-web.py:2050-2055` wirft bei `/api/github` `action="import"` einen `TypeError` bzw. nennt `TICKETS.md` (Medium). |
| **10. Keine Migration im Produktcode; funktionsfähiger Migrationsschnipsel in `docs/features/GH-48.md` (ohne Tests)** | FAIL | `docs/features/GH-48.md:180-303` | Produktcode ist frei von Dual-Read/Migrationslogik, **aber** der Migrationsschnipsel in `docs/features/GH-48.md:205-263` verliert alle Folgezeilen mehrzeiliger Beschreibungen und weicht bei der Done-Degradierung (`github` ohne `commit`) von `vibe_tickets.normalize` ab (Medium). |

## 4. Details zu Prüfaufträgen 2, 4, 5 und 6

- **Sicherheit & Robustheit (Prüfauftrag 2):**
  - Atomare Schreibwege und Konfliktbehandlung über `vibe_storage.write_text(..., expected=...)` sind in `bin/vibe_tickets.py:95-113,224-240,300-353` durchgängig eingehalten.
  - `ensure_gitignore` (`bin/vibe:2399-2401`) verweigert Symlinks (`os.path.islink(path)`) und schützt vor kaputtem UTF-8 (`UnicodeDecodeError`).
  - `bin/vibe-run.sh:513-517` nutzt `shlex.quote(str(...))` für alle Felder aus `next-package.json`; keine unvalidierte Shell-Verkettung.
  - Keine Secrets oder persönlichen Pfade im Diff gefunden.
- **Testqualität & Bestandsmodule (Prüfauftrag 4):**
  - Alle neuen und angepassten Tests stammen laut `docs/reviews/GH-48-test-agent-report.md` vom unabhängigen Test-Agenten (Rotlauf vor Implementierung mit 99 roten Fällen in §3 dokumentiert, Grünlauf nach Implementierung in §§8–9).
  - Stichprobenprüfung der überführten Bestandsmodule (`test_work_packages.py`, `test_b6_ticket_marker_states.py`, `test_ticket_feedback_processing.py`, `test_worknotes_sync.py`, `test_feedback_capture.py`, `test_tickets_ui.py`, `test_project_guide_ui.py`): Die Tests wurden inhaltlich auf `.vibe/tickets.json` und `TICKET-<ID>.json` überführt, ohne Sicherheits- oder Fachassertions zu entwerten (einzige Lücke: Substring-Assertion `"F1 eingetragen" in "FF1 eingetragen"`, siehe High-Befund).
  - `tests/verify-baseline.json` ist laut `git status --short` unverändert.
- **Import-Manifest (Prüfauftrag 5):**
  - `docs/import-manifest.json` enthält den `aenderungen`-Eintrag für `GH-48`, führt `bin/vibe_tickets.py` neu auf und entfernt `templates/common/FEEDBACK.md` sowie `templates/common/TICKETS.md`.

## Verification
- Change set reviewed: `ad00c0b..working tree` (50 geänderte getrackte Dateien, 2 gelöschte Dateien, 9 ungetrackte neue Dateien).
- Git commands run by me: `git status --short`, `git diff ad00c0b -- ...`, `git diff ad00c0b --stat -- docs/features/F15-arbeitspakete.png docs/features/F9-assistent.png`.
- Checks evidenced by supplied raw output: keine Rohausgaben im Prompt angehängt (Ergebnisse sind im Test-Agenten-Bericht `docs/reviews/GH-48-test-agent-report.md` §§3, 8, 9 dokumentiert).
- Checks reported only by the coding agent: `10 Unit-Module Ran 243 OK`, `tests.browser.test_gh48_tickets_ui Ran 3 OK`, `6 migrierte Browser-Module einzeln grün`, `test_setup_vibe Ran 50 OK`, `bash scripts/verify.sh quick` (Exit 0), `bash scripts/verify.sh package` (Exit 0).
- Checks not independently run: alle Build-, Test- und sonstigen Nicht-Git-Befehle (gemäß System-Rollenvorgabe für den strikt lesenden Review-Agenten: „Use only the read-only Git commands explicitly allowed by your permissions. Do not run builds, tests, scripts, or other shell commands.").
- Important areas inspected: `bin/vibe_tickets.py`, `bin/vibe`, `bin/vibe_packages.py`, `bin/vibe-run.sh`, `bin/vibe_issues.py`, `bin/vibe_github.py`, `bin/vibe-web.py`, `bin/vibe_guide.py`, `bin/web/app.js`, `bin/web/nova-project.js`, `scripts/setup-vibe.py`, `templates/*/AGENTS.md`, `SPEC.md`, `docs/grenzen.md`, `docs/features/GH-48.md`, `docs/import-manifest.json`, `docs/reviews/GH-48-test-agent-report.md`, `tests/unit/test_gh48_*.py`, `tests/browser/test_gh48_tickets_ui.py` sowie 7 überführte Bestands-Testmodule.
- Remaining risks: Der Abnahme-Volllauf (`bash scripts/verify.sh full`) steht wie angekündigt noch aus und muss nach Behebung der Befunde ausgeführt werden.

## Zu behebende Punkte für `PASS`
1. **[High] `bin/vibe-web.py:1790-1794`**: Doppeltes Präfix in `f"B{num} eingetragen"` / `f"F{num} eingetragen"` beheben (`add_bug`/`add_feedback` liefern bereits `"B1"`/`"F1"`).
2. **[Medium] `bin/vibe-web.py:2050-2055`**: `action == "import"` in `/api/github` an den `int`-Rückgabewert `added` von `vibe.github_issues_import` anpassen (verhindert `TypeError` bei `", ".join(added)`) und `TICKETS.md unverändert.` durch `Ticketspeicher unverändert.` ersetzen.
3. **[Medium] `docs/features/GH-48.md:205-263,306-308`**: Migrationsschnipsel für mehrzeilige `Beschreibung:`-Blöcke und `done`-Tickets mit `github`-Bezug (ohne `commit`) korrigieren sowie den veralteten Hinweis unter `## Grenzen` zur offenen Testmigration aktualisieren.
4. **(Empfohlen, Minor)** `_type_rank`-Ordnung in `bin/vibe_packages.py:378` / `docs/features/GH-48.md` abgleichen, Rest-Hinweistexte in `bin/vibe:24` und `bin/web/app.js:355,1108` aktualisieren und Status der beiden geänderten Screenshots `F15-arbeitspakete.png` / `F9-assistent.png` klären.

Verdict: CHANGES REQUIRED
