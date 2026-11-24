# GH-56 — Unabhängiges Codereview

**Arbeitspaket:** GH-56 — UI-Anpassung der Projektansicht „Work"
**Branch:** `feature/m0p/gh-56`
**Reviewer:** `code-reviewer` (unabhängig)
**Dokumentation des Ergebnisses:** Koordinator (der Reviewer konnte die Datei selbst wegen `shell: permission denied` nicht schreiben; Inhalt und Verdict stammen unverändert aus dem Review).

## Scope

Geprüft wurde der Diff des Arbeitspakets gegen `HEAD` sowie die neuen Dateien:

- `bin/vibe-web.py`, `bin/vibe_tickets.py` (Backend: manuelles Schließen, Zustandsübergänge)
- `bin/web/nova-core.js`, `bin/web/nova-project.js`, `bin/web/nova-widgets.js`, `bin/web/nova.css` (Work-Ansicht, Editor, Design)
- `docs/import-manifest.json`, `docs/features/GH-56.md`
- Vertragsquellen: `TICKET-GH-56.json`, `SPEC.md`, `AGENTS.md`, `docs/features/GH-56-design-notes.md`
- Testvertrag (nur lesend): `tests/browser/test_gh56_work_ui.py`, `docs/reviews/GH-56-test-agent-report.md`

## Prüfpunkte und Befunde

### Backend-Invariante (GH-48) — OK

- `WEB_TICKET_STATES` (`bin/vibe-web.py:98`) und `web_ticket_state()` (`:101`) bleiben unverändert; `action:"state"` lehnt `done`, `blocked` und `waiting-merge` weiterhin mit Klartext ab.
- `ticket_set_state()` (`:114`) verweigert Zustandswechsel an erledigten Tickets; die Antwort erfolgt als HTTP 200 mit `ok:false` statt eines technischen Fehlers.
- Die neue Aktion `action:"close"` verlangt strikt `confirm is True` (`bin/vibe-web.py`, `/api/ticket`-Handler ca. `:1789–1886`). Damit ist die doppelte Absicherung (native `window.confirm` im UI + serverseitiges Flag) erfüllt.
- `vibe_tickets.close()` (`bin/vibe_tickets.py:333`) nutzt `normalize(..., require_done_proof=False)` ausschließlich im menschlichen Schließpfad. Der Läufer-/Sync-Pfad (`update`, `:301`) behält die Nachweis-Invariante; `delete` (`:366`) schützt erledigte Tickets. Kein Weg, ein geschlossenes Ticket zu bearbeiten oder wieder zu öffnen, wurde gefunden.

### Frontend-Korrektheit — OK

- Board: `div[data-nv-board]` mit den drei Spalten `draft|ready|running`; Rohzustand in `data-nv-state` über `nvpRawState()` (`nova-project.js:83–93`), Spaltenzuordnung über `nvpColOfState()` (`:95–100`). Jede Karte genau einmal.
- DnD: optimistisches Verschieben mit anschließender Zustands-/Prioritäts-Persistenz, Rollback im Fehlerfall; `div[data-nv-board-ghost]` und `div[data-nv-drop-marker]` werden bei `dragend` bzw. Fehler zuverlässig entfernt. Tastaturalternativen über Buttons/↑↓ vorhanden.
- Filter: Zustands-Chips mit `aria-pressed`, zweiter Klick setzt zurück; Suche und Typ-Chips wirken auf Board und Liste; der Done-Chip überstimmt den „Erledigte anzeigen"-Schalter (`nvpWireWorkFilters`, ca. `:1173`).
- Priorisierung: `nvpRawState(row) !== 'open'` (`:962`) schränkt den Strip auf Ready-Tickets ein; Speicherung über die bestehende AP11-API.
- Mobile: `div[data-nv-work-list]` ohne Board im DOM; Editor-Vollbild über CSS `@media (max-width:768px)`.
- Editor: `NV.editView` mit `data-nv-ticket-editor`, `sessionStorage['nv-editview-width']`, Resize am Rand; `window.confirm` beim Schließen; `ticket-copy` öffnet einen vorbelegten Draft (`nova-widgets.js` / `nova.css` / `nova-project.js`).
- i18n: neue deutsche Quellschlüssel besitzen EN-Übersetzungen im `VIBE_I18N.extend`-Block am Ende von `nova-project.js`; DE/EN-Identitätspaare vorhanden.

### Regressions- und Dokumentationsprüfung — OK

- `nvpStateLabel` erhält überall den Anzeigezustand (`row.state`, z. B. „erledigt"), nicht den Rohzustand — die befürchtete Fehlbeschriftung „Offen" für `done` besteht nicht (`nova-project.js:144–153`, `:684`, `:2258`).
- Die Änderung in `nova-core.js` schließt die offene Edit-View beim Routenwechsel; das löst die Scrim-Blockade, ohne die GH-57-Settings-Editview zu verändern.
- `docs/features/GH-56.md` beschreibt die Design-Entscheidung `close` statt `state:done` mit korrekter Begründung (GH-48-Schutz) und deckt sich mit dem Code.

## Einordnung nicht-blockierender Punkte

- Der noch offene Browserfall `test_17_consistent_spacing_grid` (`float("12px")`) ist ein nachgewiesener **Testcode**-Defekt, kein Implementierungsfehler; er wird vom Test-Agenten korrigiert.
- Legacy-Browserfälle (AP22/F33/F34) prüfen die frühere F34-Ansicht („kein Board", flache Liste, Formular im Kontext-Panel). GH-56 ist die neue autoritative Vorgabe; der Test-Agent migriert diese Fälle auf den neuen Vertrag. Kein Code-Fehler.
- `docs/features/F15-arbeitspakete.png` wurde durch einen Legacy-Screenshot-Test überschrieben und ist kein Paketartefakt; der Koordinator stellt die Datei vor dem Commit aus `HEAD` wieder her.

## Durchgeführte Prüfungen (vom Coding-Agenten ausgeführt, vom Reviewer bewertet)

| Befehl | Ergebnis |
| --- | --- |
| `python3 scripts/check-import-manifest.py && python3 scripts/check-syntax.py && python3 scripts/check-no-secrets.py` | OK — 71 Dateien im Manifest, 261 Python-/8 Bash-/5 JSON-Dateien syntaktisch OK, keine Geheimnisse |
| `python3 -m unittest tests.unit.test_gh48_web_api -v` | `Ran 11 tests` — OK |
| `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_gh56_work_ui -v` | 20 von 21 bestanden; 1 Testcode-Defekt (siehe oben), vom Test-Agenten korrigiert |
| `bash scripts/verify.sh package` | OK (Exit 0) |

## Nachtrag (nach dem Review)

Der Test-Agent hat nach der Legacy-Test-Migration einen echten Defekt D1 gefunden:
Beim Öffnen des Ticket-Editors aus dem Kontext-Panel blockierte der
`nv-context-scrim` den Speichern-Button. Der Coding-Agent hat ihn minimal
behoben (`NV.context.close()` vor `NV.editView.open()` in `nvpOpenTicketForm`);
danach wurden die betroffenen Suites erneut ausgeführt. Zusätzlich hat der
Test-Agent veraltete AP22-Fixture-IDs (`AP-OPEN` o. ä.) auf die GH-48-ID-Regel
umgestellt (ohne die ID-Validierung zu lockern).

| Befehl (jeweils mit `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright`) | Ergebnis |
| --- | --- |
| `python3 -m unittest tests.browser.test_gh56_work_ui -v` | `Ran 21 tests` — OK |
| `python3 -m unittest tests.browser.test_ap22_work_ui -v` | `Ran 8 tests` — OK |
| `python3 -m unittest tests.browser.test_f33_project_ui -v` | `Ran 29 tests` — OK |
| `python3 -m unittest tests.browser.test_f34_project_ui -v` | `Ran 34 tests` — OK |

Damit sind alle bekannten Befunde behoben und regressionsgeprüft.

## Fazit

Keine blockierenden Befunde. Die Umsetzung erfüllt die Akzeptanzkriterien von GH-56 und bewahrt die GH-48-Zustandsinvariante.

Verdict: PASS
