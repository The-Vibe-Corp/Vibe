# GH-56 — Test-Agent-Report: Projektansicht „Work“

Status: Tests geschrieben, rot vor der Implementierung ausgeführt und nach
der Implementierung grün (21/21).
Quelle der Fälle: `TICKET-GH-56.json` (Akzeptanzkriterien und Anforderungsabschnitte)
und `SPEC.md`. Die Fälle wurden unabhängig aus dem Arbeitspaket abgeleitet,
nicht aus einem Implementierungsdiff. Ergänzende DOM-Verträge stehen in
`docs/features/GH-56-design-notes.md` (Notizen eines vorherigen Laufs); die
Test-datei dokumentiert dieselben Hooks in ihrem Moduldocstring.

Getestete Datei: `tests/browser/test_gh56_work_ui.py` (21 Fälle, eine Klasse
`GH56WorkBrowserTest`). Der Test-Agent hat ausschließlich diese Testdatei und
diesen Report geändert. Produktionsdateien wurden nicht berührt.

## Grün-Lauf nach der Implementierung

Befehl (exakt ausgeführt):

```sh
cd ~/vibe-logs/worktrees/vibe-GH-56-5KVM0L && PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_gh56_work_ui -v
```

Ergebnis: **`Ran 21 tests in 76.456s — OK`** (21/21 bestanden). Log außerhalb
des Repos: `/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/gh56-green-run.log`.

Zwischenfall im Testcode (kein Implementierungsfehler): In Test 17 wurde
`getComputedStyle(...).padding` mit `float("12px")` geparst und löste einen
`ValueError` aus. Der Test-Agent hat das Parsing auf `float(x[:-2])` für
px-Werte korrigiert. Die fachliche Assertion blieb unverändert (px-basiert,
durch 4 teilbar, höchstens vier verschiedene Werte); danach lief der ganze
Module grün.

## Testfälle (Name / Vorbedingung / Aktion / erwartetes Ergebnis)

| # | Name | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|------|--------------|--------|---------------------|
| 01 | `test_01_board_columns_and_tickets_by_state` | Tickets in draft/open/in-progress/blocked/waiting-merge/done | Work öffnen (1500×1100) | `div[data-nv-board]` mit den drei Spalten `draft`, `ready`, `running`; jede Karte genau einmal in der passenden Spalte (blocked/waiting-merge → ready), done verborgen; Überschriften vorhanden und unterscheidbar |
| 02 | `test_02_card_badges_actions_and_full_title` | Karten in allen Zuständen, einer mit langem Titel | Work öffnen, `ticket-details` der langen Karte klicken | Running-/Blocked-/Ready-for-Merge-Badges nur an passenden Karten; Details auf allen, Resume nur bei in-progress/blocked/waiting-merge; Titel `.nv-ticket-title` mit `overflow:hidden`/`text-overflow:ellipsis`, vollständiger Titel im Detail-Panel |
| 03 | `test_03_drag_draft_to_ready_updates_state` | AP3 in Draft | HTML5-Drag von AP3 nach Ready | Store `state=open`; Karte in Ready-Spalte |
| 04 | `test_04_drag_ready_to_draft_updates_state` | AP1 in Ready | HTML5-Drag von AP1 nach Draft | Store `state=draft`; Karte in Draft-Spalte |
| 05 | `test_05_drag_shows_ghost_and_drop_marker` | Draft- und Ready-Karte | `dragstart` + `dragover` ohne `drop`, danach `dragend` | `div[data-nv-board-ghost]` und `div[data-nv-drop-marker]` sichtbar, danach entfernt; kein Statuswechsel ohne Drop |
| 06 | `test_06_failed_state_change_rolls_back` | AP3 in Draft, `/api/ticket` antwortet 500 | Drag Draft→Ready | Optimistische Änderung wird zurückgerollt: Karte bleibt in Draft, Store bleibt `draft`; Request wurde tatsächlich gesendet |
| 07 | `test_07_vertical_board_reorder_persists` | Drei Ready-Karten | Oberste Karte per DnD hinter die beiden anderen ziehen, anschließend Reload | DOM-Reihenfolge kippt, `/api/priority` enthält dieselbe Reihenfolge, bleibt nach Reload erhalten |
| 08 | `test_08_priority_strip_keyboard_reorder_persists` | Zwei Ready-Karten | `priority-down` der ersten Strip-Zeile | Strip und gespeicherte Priorität kippen übereinstimmend (Tastaturalternative) |
| 09 | `test_09_state_chips_cover_all_states_and_reset` | Je eine Karte in draft/open/in-progress/done | State-Chips einzeln klicken und erneut klicken | Genau der gefilterte Status sichtbar; `aria-pressed=true` am aktiven Chip; zweiter Klick setzt zurück |
| 10 | `test_10_search_filters_board_and_can_be_cleared` | Zwei unterscheidbare Titel | `input[data-nv-work-search]` füllen und leeren | Nur Treffer sichtbar, Filterwert erkennbar, Leeren stellt beide wieder her |
| 11 | `test_11_done_hidden_toggle_and_not_editable` | Ein erledigtes Ticket mit Nachweis | Work öffnen, „Erledigte anzeigen“, Karte anklicken; zusätzlich direkter `POST /api/ticket action=state` | Zunächst verborgen, danach sichtbar; Detail ohne `ticket-edit` und ohne `[data-nv-field]`; Backend lehnt Wiedereröffnung ab |
| 12 | `test_12_close_requires_confirmation` | Offenes Ticket AP1 | `ticket-close` (alternativ Legacy `package-close`) klicken, Dialog abbrechen, erneut klicken und bestätigen | Bestätigungsdialog mit Rückfrage; Abbruch ändert nichts; Bestätigung setzt `state=done`, Karte dann verborgen |
| 13 | `test_13_copy_done_ticket_creates_draft` | Erledigtes Ticket mit Beschreibung | Karte einblenden, `ticket-copy`, Editor speichern | Neuer Eintrag mit `state=draft` und übernommenem Titel; Original bleibt `done` |
| 14 | `test_14_new_ticket_starts_draft_and_is_visible` | Leerer Ticketspeicher | `new-package`, Titel/Beschreibung füllen, `ticket-save` | Genau ein neuer Eintrag mit `state=draft`, Karte in Draft-Spalte, `data-nv-state=draft` |
| 15 | `test_15_editor_default_width_and_full_height` | Desktop 1500×1100 | `new-package` öffnen | Editor-Aside ≥400 px breit, ≥95 % der Viewporthöhe, oben bündig; Titel/Beschreibung/Save/Cancel vorhanden |
| 16 | `test_16_resized_editor_width_persists_during_session` | Desktop, Editor offen | Linken Editor-Rand per Maus 140 px nach links ziehen, zu `#/settings` und zurück navigieren, Editor erneut öffnen | Vergrößerte Breite bleibt ohne Reload erhalten (±6 px) |
| 17 | `test_17_consistent_spacing_grid` | Desktop-Work mit Karte und offenem Editor | Berechnete `padding`/`gap`-Werte von Karte, Spalte, Filterleiste und Editor auslesen | `--nv-space-1..3` vorhanden; alle gemessenen Abstände auf 4px-Raster |
| 18 | `test_18_mobile_shows_list_instead_of_board` | Drei Tickets, viewport 600×800 | Work öffnen | Kein `div[data-nv-board]`; `div[data-nv-work-list]` mit allen nicht erledigten Karten und Suchfeld |
| 19 | `test_19_mobile_priority_view_ready_only` | Draft, Ready, Running; viewport 600×800 | Work öffnen | Priorisierungszeilen enthalten ausschließlich die Ready-ID |
| 20 | `test_20_mobile_fullscreen_editor_matches_desktop` | viewport 600×800 | `new-package` öffnen | Editor bedeckt ≥95 % von Breite und Höhe; enthält dieselben Kernfelder/-aktionen wie Desktop |
| 21 | `test_21_mobile_filters_work_on_list` | Paket und Bug; viewport 600×800 | Suche füllen/leeren, Bug-Chip, Alle-Chip | Suche und Chips filtern die Liste; Reset zeigt wieder beide Karten |

Die Fixtures liegen ausschließlich im isolierten `.vibe/tickets.json` des
Testprojekts. Alle VIBE_*/SANDBOX_-Variablen der laufenden Instanz werden
entfernt; Server läuft auf einem freien Port mit eigenen Temp-Pfaden.

## Rot-Lauf (exakt ausgeführter Befehl)

```sh
cd ~/vibe-logs/worktrees/vibe-GH-56-5KVM0L && PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_gh56_work_ui -v
```

Ergebnis (beobachtet, 2026-11-24):

```text
Ran 21 tests in 148.747s
FAILED (failures=1, errors=20)
```

Umgebung: **funktionsfähig**. Der isolierte `vibe-web`-Server startete, der
Token wurde erzeugt, Chromium startete headless, die Work-Route
(`main#nv-main[data-nv-view='project']`, `section[data-nv-ppanel='work']`) war
in jedem Fall erreichbar. Es gab keine Environment- oder Fixture-Fehler.

Fachliches Rot, nach Ursache gruppiert:

* **20 ERROR** — `TimeoutError: waiting for locator("div[data-nv-board]").first
  to be visible` (Fail 01–11, 14, 17), `waiting for
  locator("aside[data-nv-ticket-editor]").first to be visible` (Fail 15, 16,
  20) bzw. `waiting for locator("div[data-nv-work-list]").first to be
  visible` (Fail 18, 21). Ursache: Die aktuelle Ansicht ist noch die alte
  Liste; es gibt kein Board, keine dedizierte Editor-Aside und keine mobile
  Listencontainer. Die Fälle scheitern am **fehlenden DOM-Vertrag**, nicht an
  Test-Setup oder -Daten. Fail 08 wartet zusätzlich am Board, obwohl die
  bestehende Priorisierungsleiste vorhanden wäre — der Board-Check ist
  bewusst Teil des neuen Vertrags.
* **1 FAIL** — `test_19_mobile_priority_view_ready_only`: reale fachliche
  Abweichung. Erwartet `['AP1']` (nur Ready), tatsächlich
  `['AP3', 'AP1', 'AP2']`. Die bestehende mobile Priorisierung zeigt auch
  Draft- und Running-Tickets und verletzt damit die Akzeptanzkriterien
  „Priorisierungsansicht ausschließlich für Ready“ (Ticket Abschnitt Mobile).

Damit ist der Rot-Status für die erwartete fehlende Umsetzung nachgewiesen;
einzig Fall 19 lief bis zur fachlichen Assertion.

## Abdeckungsmatrix Akzeptanzkriterium → Test

| Akzeptanzkriterium (Ticket) | Test(s) |
|-----------------------------|---------|
| 1. Sidebar breiter, vollhöhenfähig, per Drag verstellbar, Breite in Session | 15, 16 |
| 2. Desktop-Kanban mit Draft/Ready/Running | 01 (zusätzlich 02 Badges/Kacheln) |
| 3. DnD Draft↔Ready ändert Status | 03, 04 (Feedback 05, Rollback 06) |
| 4. Vertikales Verschieben ändert Priorität und persistiert | 07 (Tastatur-Alternative 08) |
| 5. Filter und Suche funktionieren, alle Status, Resetbar | 09, 10, 21 |
| 6. Mobile Liste statt Board | 18 |
| 7. Mobile Priorisierung nur Ready | 19 |
| 8. Mobile Vollbild-Bearbeitung | 20 (Felder/Aktionen wie Desktop) |
| 9. Geschlossene ausgeblendet, einblendbar, nicht bearbeitbar | 11, 12 (Absicherung) |
| 10. Geschlossene als neues Draft kopierbar | 13 |
| 11. Neue Tickets immer Draft | 14 |
| 12. Konsistente Abstände | 17 |

Zentrale Anforderungen ohne eigenes Akzeptanzkriterium: Status-Badges,
Details/Resume und Titel-Ellipsis (02), DnD-Feedback/Rollback (05, 06),
Filter auf Mobile (21), Backend-Schutz gegen Wiedereröffnung (11),
Tastaturbedienbarkeit der Priorisierung (08).

## Hinweise für den Coding-Agenten (erwartete Hooks und Verträge)

1. **Board:** `div[data-nv-board]` > `article[data-nv-col='draft|ready|running']`
   > `div[data-nv-col-cards]` > `article[data-nv-ticket='<id>']`. Die Spalten
   tragen `data-nv-col`; Karten tragen `data-nv-state` mit dem **Rohzustand**
   (`draft`, `open`, `in-progress`, `blocked`, `waiting-merge`, `done`), nicht
   nur den deutschen Anzeige-String aus `display_state`. `blocked` und
   `waiting-merge` werden auf der Ready-Spalte sichtbar gehalten, `done` nur
   nach Toggle. Die Spaltenüberschriften müssen vorhanden und unterschiedlich
   sein; die konkrete Sprache wird nicht geprüft.
2. **Karten:** `.nv-ticket-title` mit `text-overflow:ellipsis` und
   `overflow:hidden`; `button[data-nv-action='ticket-details']` auf jeder
   Karte; `button[data-nv-action='ticket-resume']` bei in-progress/blocked/
   waiting-merge. Status-Badges als sichtbarer Text (Englisch „Running“,
   „Blocked“, „Ready for Merge“; deutsche Entsprechungen werden akzeptiert)
   nur bei zutreffendem Status. Das Detail-Panel bleibt
   `[data-nv-ticket-detail='<id>']` (Bestand).
3. **DnD:** `draggable="true"` auf den Karten; die Tests dispatchen
   `DragEvent('dragstart'|'dragover'|'drop'|'dragend')` mit einer
   `DataTransfer` direkt im DOM. `dragover` muss
   `div[data-nv-board-ghost]` (an `document.body`) und
   `div[data-nv-drop-marker]` erzeugen; `dragend` entfernt beides wieder.
   Draft↔Ready → `POST /api/ticket {name, action:'state', id, state}`
   (`draft`↔`open`), optimistisch mit Rollback bei Fehler. Drop innerhalb
   derselben Spalte → `POST /api/priority {name, action:'set', order}`;
   `GET /api/priority?name=...` liefert `order` als Liste von Objekten mit
   `id`. Die Reihenfolge muss nach Reload stimmen.
4. **Filter:** `button[data-nv-work-state='draft|ready|running|done']` mit
   `aria-pressed` (aktiver Chip = „true“), zweiter Klick setzt zurück.
   Bestehende Hooks `input[data-nv-work-search]`,
   `button[data-nv-work-hide-done]`, `button[data-nv-work-kind]` wirken
   identisch auf Board und mobile Liste. Der `done`-Chip muss erledigte
   Karten auch dann zeigen, wenn der „Erledigte anzeigen“-Schalter noch
   aus ist.
5. **Editor/Sidebar:** `aside[data-nv-ticket-editor]` (ohne `data-nv-editview`
   zusätzlich möglich), Felder `input[data-nv-field='title']`,
   `textarea[data-nv-field='description']`, optional
   `[data-nv-field='state']` (muss dann `draft` vorbelegen), Aktionen
   `button[data-nv-action='ticket-save'|'ticket-cancel'|'ticket-close'|'ticket-copy']`.
   Desktop: ≥400 px bei 1500 px Viewport, volle Höhe. Resize: Der Test
   zieht mit der Maus am linken Rand der Aside; Breite in `sessionStorage`
   halten und nach Hash-Navigation (kein Reload) wiederverwenden. Mobile
   (≤768 px): gleicher Editor als Vollbild-Overlay.
6. **Geschlossene:** Schließen über `ticket-close` oder den bestehenden
   `package-close` in Detail/Editor; `window.confirm` mit klarer Rückfrage
   (Abbruch = keine Änderung, Bestätigung = `state=done`). Kopie über
   `ticket-copy`: Editor vorbefüllt, Speichern erzeugt ein neues Ticket mit
   `state=draft` und lässt das Original unverändert. Erledigte dürfen keine
   Editierfelder/-aktionen anbieten; `POST /api/ticket action=state` lehnt
   sie bereits backendseitig ab (Bestand, bitte erhalten).
7. **Design-Tokens:** `--nv-space-1`, `--nv-space-2`, `--nv-space-3` auf
   `:root`; gemessene `padding`/`gap`-Werte von Karte, Spalten-Container,
   Filterleiste und Editor liegen im 4px-Raster. Der 4px-Raster-Wert ist
   eine Prüfschwelle für „einheitliche Abstände“, keine fachliche Vorgabe
   des Tickets.
8. **Breakpoint:** 769 px (Desktop ≥769, Mobile ≤768), geprüft mit
   1500×1100 und 600×800.

## Bewusste Abdeckungsgrenzen

* **Nur Chromium** (headless). Keine Firefox-/Safari-/Touch-Geräte-Prüfung;
  Touch-Target-Größen und Screenreader-Verhalten wurden nicht gemessen.
* **Tastatur-DnD auf dem Board** ist nicht separat geprüft. Das Ticket
  verlangt Tastaturbedienbarkeit „soweit im bestehenden UI-System möglich“;
  abgedeckt ist die vorhandene ↑/↓-Alternative der Priorisierungsleiste
  (Test 08), nicht eine eigene Board-Tastatur-DnD-Implementierung.
* **Loading-/Empty-/Error-Zustände** sind nur teilweise geprüft: Rollback
  (Test 06) und leerer Speicher (Test 14) ja, visuelle Ladeindikatoren oder
  Fehlermeldungen nein.
* **Exakte Visual-/Spacing-Werte** werden nur über das 4px-Raster und die
  Token-Präsenz approximiert (Test 17), nicht pixelgenau gegen ein Design.
* **Neue Tickets über `new-bug`/`new-feedback`** werden nicht separat
  geprüft; Test 14 deckt die geforderte Draft-Regel für `new-package` ab.

## Korrekturen am Kandidaten-Test (vorheriger Lauf)

Der uncommittete Kandidat `tests/browser/test_gh56_work_ui.py` enthielt sieben
Fälle. Kritisch geprüft und korrigiert wurden u. a.:

* sinnlose Assertion `assertIn("data-nv-col", get_attribute("data-nv-col"))`
  ersetzt durch Exaktvergleich und echte Spalten-Platzierung;
* fehlende Abdeckung ergänzt: Sidebar (15, 16), mobiler Vollbild-Editor
  (20), Kopie (13), Suche (10), DnD-Richtung Ready→Draft (04), DnD-Feedback
  (05), Rollback (06), Badges/Aktionen/Titel (02), Schließen mit Rückfrage
  (12), Abstände (17), mobile Filter (21), vertikales Board-DnD (07);
* der bisherige „vertical order in running“-Fall nutzte die Priorisierungs-
  leiste statt des Boards und trug einen irreführenden Namen; jetzt
  getrennt in Board-DnD (07) und Tastatur-Priorisierung (08);
* Isolierung verschärft: alle VIBE_*/SANDBOX_-Variablen entfernt, eigene
  TMPDIR-/TMUX-Pfade, Server-Log im Temp-Verzeichnis, Bestätigungsdialoge
  deterministisch gesteuert.

## Nachweise / Sonstiges

* Syntaxprüfung: `python3 -m py_compile tests/browser/test_gh56_work_ui.py` →
  erfolgreich.
* Rot-Lauf-Log (außerhalb des Repositories):
  `/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/gh56-red-run.log`.
* Dieses Dokument enthält kein Pass-Verdikt; die Bewertung erfolgt durch den
  Reviewer nach der Umsetzung.
* Branch: `feature/m0p/gh-56`. Der Test-Agent hat nicht gestagt, nicht
  committet, nicht gepusht und keine Produktionsdatei geändert.
* Während des Rot-Laufs bzw. unmittelbar danach sind fremde, noch
  uncommittete Änderungen in `bin/vibe-web.py` und `bin/web/nova-widgets.js`
  aufgetaucht (mtime 09:13–09:14 Uhr, nach Erstellung der Testdatei um
  09:11 Uhr und nach Ende des Rot-Lauf-Logs um 09:14:04 Uhr). Der Rot-Lauf
  lief gegen den Stand **vor** diesen Änderungen. Diese Änderungen stammen
  nicht vom Test-Agenten und wurden nicht verändert. Erste Sichtprüfung:
  sie führen `data-nv-ticket-editor` am bestehenden Editview-Aside und
  `action:"close"` mit `confirm:true` ein; beides ist mit den Testverträgen
  vereinbar. Die vorhandene Mobile-CSS (`@media (max-width:768px)` mit
  `.nv-editview { width:100vw !important; height:100vh }`) erfüllt den
  Vollbild-Vertrag von Test 20. Der Grün-Lauf oben erfolgte erst nach Abschluss der Implementierung, nicht unmittelbar nach dem Rot-Lauf.

## Migration alter Verträge (GH-56 ist autoritativ)

Alle unten genannten Suites wurden zunächst **unverändert** ausgeführt und die
Fehler klassifiziert. Anschließend wurden ausschließlich Testdateien angepasst.
Fachliche Absichten (Anlegen, Bearbeiten, Löschen, Feedback, Priorisierung,
Suche, Filter, Nachweise) wurden erhalten; reine Layout-Details ohne Fachwert
wurden entfernt und sind unten begründet.

| Suite | alter Anspruch | neuer Anspruch (GH-56) | Ergebnis |
|-------|----------------|------------------------|----------|
| `test_ap22_work_ui.py` | kein Board, `div[data-nv-ticket-list]`, Anzeigestatus „offen/BLOCKIERT/ohne Nachweis“, Formular im Kontext-Panel, Markdown-Fixtures, IDs ohne Ziffernsuffix | Board mit drei Spalten, Rohzustand am Kartenattribut, Formular im `aside[data-nv-ticket-editor]`, JSON-Ticketspeicher, State-Chips, IDs nach GH-48-Regel | `Ran 8 — OK` |
| `test_f33_project_ui.py` | Board-Absence, Liste, Formular im Kontext-Panel, Strip mit Draft/Running, globale AGENTS.md im `details` | Board, Editor, Strip nur `open`, AGENTS.md über Bearbeiten-Knopf + `textarea[data-nv-agents-text]`; Long-Description in der Detailansicht | `Ran 29 — OK` |
| `test_f34_project_ui.py` | Board-Absence, Liste, Strip mit Draft/Running, Done-Suchtreffer trotz Hide-Done sichtbar | Board, Strip nur Ready, Done nur über Toggle/Done-Chip, Rohzustände, JSON-Fixtures | `Ran 34 — OK` |
| `test_ap22_advanced_ui.py` | — (Strip im Work-Tab, Ready-Filter) | unverändert gültig | `Ran 10 — OK` (keine Änderung nötig) |
| `test_gh48_tickets_ui.py` | — | unverändert gültig | `Ran 3 — OK` (keine Änderung nötig) |
| `test_tickets_ui.py` | — | unverändert gültig | `Ran 3 — OK` (keine Änderung nötig) |
| `test_feedback_ui.py` | — | unverändert gültig | `Ran 3 — OK` (keine Änderung nötig) |
| `test_f34_questions_ui.py` | — (Kontext-Panel für Fragen, nicht Ticketformular) | unverändert gültig | `Ran 17 — OK` (keine Änderung nötig) |

### Was konkret geändert wurde

* **Fixtures:** Alle drei migrierten Suites schreiben ihre Tickets jetzt als
  `{"version": 1, "tickets": [...]}` nach `.vibe/tickets.json` (GH-48) statt
  in `TICKETS.md`/`FEEDBACK.md`. Helfer `ticket_text`/`feedback_text` und
  ID-/Typprüfungen lesen den JSON-Speicher; die artenbasierten Zusagen
  (`package|bug|feedback`) blieben erhalten.
* **Board statt Liste:** `div.nv-ticket-list[data-nv-ticket-list]` und
  „Board darf nicht existieren“-Assertion wurden durch
  `div[data-nv-board]` mit drei `article[data-nv-col]` ersetzt.
  `data-nv-state` wird jetzt als Rohzustand geprüft.
* **Editor statt Kontext-Panel:** Formular-, ID-Hinweis- und Cancel-Fälle
  adressieren `aside[data-nv-ticket-editor]`; das Schließen vor dem nächsten
  Aktionsknopf nutzt `[data-nv-editview-close]`. Details bleiben im
  Kontext-Panel (`[data-nv-ticket-detail]`).
* **Priorisierung nur Ready:** F34/F33-Prio-Fälle nutzten den Draft F5 als
  erstes Element. Sie wurden auf die Ready-IDs F7/F8/B7/F1 umgestellt;
  `expected_effective_ids()` filtert jetzt auf `state in ("offen","open")`.
  Ein eigener Test stellt explizit sicher, dass der Draft F5 **nicht** im
  Strip erscheint. DnD-, ↑/↓-, Badge-, Persistenz- und Kein-Voll-Neurender-
  Zusagen blieben unverändert erhalten.
* **Entfernte Layout-Details ohne Fachwert:** F33
  `test_form_opens_directly_under_the_action_bar` prüfte die DOM-Position des
  Formulars relativ zur alten Ticketliste; das Formular ist jetzt ein Vollhöhen-
  Editor. Erhalten wurden Sichtbarkeit im Viewport und die Kernfelder.
  F34 `test_integrated_list_and_kinds` verglich eine exakte Kartenreihenfolge;
  die Reihenfolge wird in den Priorisierungsfällen geprüft, hier wurde auf
  `assertCountEqual` (vollständige Menge) umgestellt.
* **Geänderte Fachlichkeit bewusst übernommen:** F34
  `test_work_search_finds_done_and_filters` erwartete bisher, dass ein
  Suchtreffer erledigte Tickets trotz „Erledigte ausblenden“ einblendet.
  GH-56 verlangt, dass Erledigte nur über Button/Filter erscheinen. Der Fall
  prüft jetzt Suche + Done-Chip + Reset. F33s Global-AGENTS-Test nutzt den
  aktuellen Bearbeiten-Knopf und `textarea[data-nv-agents-text]` statt des
  entfernten `details[data-nv-global-agents]`.

### Ehemaliger Implementierungsdefekt D1 (vom Coding-Agenten behoben)

**D1 — Kontext-Scrim blockierte das Ticket-Formular im Editor.**
Der Coding-Agent hat `NV.context.close()` vor `NV.editView.open()`
ergänzt. Die Tests wurden dafür nicht verändert; der Defekt ist behoben.
Ursprünglicher Nachweis:

* `tests.browser.test_ap22_work_ui.DeleteTest...` bzw.
  `EditTest.test_edit_prefills_and_saves_only_the_chosen_ticket`:

  ```text
  playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
    - waiting for locator("[data-nv-ticket-form]").locator("[data-nv-action='ticket-save']")
      - <div class="nv-context-scrim" data-nv-context-scrim=""></div> intercepts pointer events
  ```

* `tests.browser.test_f33_project_ui.WorkOrderTest.test_feedback_edit_posts_update`:

  ```text
  playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
    - waiting for locator("[data-nv-ticket-form]").locator("button[data-nv-action='ticket-save']")
      - <div class="nv-context-scrim" data-nv-context-scrim=""></div> intercepts pointer events
  ```

Auslöser: Karte anklicken → Details im Kontext-Panel → „Bearbeiten“ öffnet
den GH-56-Editor, das Kontext-Panel bleibt aber mit seinem Scrim darüber. Der
Benutzer konnte „Speichern“ nicht klicken; Korrektur wie oben beschrieben.

### Tatsächlich ausgeführte Befehle

Für jede Suite (aus dem Worktree):

```sh
PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.<modul> -v
```

Ergebnisse der letzten Läufe: `test_gh56_work_ui` 21/21 OK,
`test_ap22_work_ui` 8/8 OK, `test_f33_project_ui` 29/29 OK,
`test_f34_project_ui` 34/34 OK, `test_ap22_advanced_ui` 10/10 OK,
`test_gh48_tickets_ui` 3/3 OK, `test_tickets_ui` 3/3 OK,
`test_feedback_ui` 3/3 OK, `test_f34_questions_ui` 17/17 OK.
Logs liegen außerhalb des Repos unter
`/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/legacy_*_final.log`.

## Finale Nachprüfung: Fixture-Rename und Grün-Lauf

Auslöser: `tests/browser/test_ap22_work_ui.py` verwendete die Fixture-Kennungen
`AP-OPEN`, `AP-OPEN2` und `AP-BLOCK`, die gegen die GH-48-ID-Regel
`^[A-Za-z][A-Za-z0-9_-]*[0-9]+$` verstoßen. `vibe_tickets.update` lehnte das
Speichern mit `Ungültige Ticket-ID: 'AP-OPEN'` ab. Die ID-Validierung wurde
bewusst **nicht** gelockert (GH-48 bleibt unangetastet); stattdessen wurden
im Test konsistent umbenannt:

| alt | neu |
|-----|-----|
| `AP-OPEN` | `AP-101` |
| `AP-OPEN2` | `AP-102` |
| `AP-BLOCK` | `AP-103` |
| `AP-DONE` (ebenfalls ohne Ziffernsuffix) | `AP-104` |

Betroffen waren Fixtures, Erwartungsmaps, Detail-/Bearbeiten-/Löschfälle, der
Priorisierungsfall, der geänderte Titel und alle Docstrings. `BUG-7` und
`FB-1` erfüllen die ID-Regel bereits und blieben unverändert.
Zusätzlich wurde im Bearbeitungsfall die Titel-Erwartung an das bestehende,
bewusste Editor-Verhalten angepasst: Ein redundanter `AP-101 `-Prefix wird vor
dem Speichern entfernt, im Speicher steht daher `Geändertes Paket`. Die
fachliche Prüfabsicht (nur das gewählte Ticket wird geändert) blieb erhalten.

Exakt ausgeführte Befehle (jeweils aus dem Worktree):

```sh
PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_ap22_work_ui -v
PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_gh56_work_ui -v
PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 -m unittest tests.browser.test_f33_project_ui -v
```

Beobachtete Ergebnisse:

```text
test_ap22_work_ui: Ran 8 tests in 70.278s — OK
test_gh56_work_ui: Ran 21 tests in 87.179s — OK   (letzte Bestätigung nach Rename)
test_f33_project_ui: Ran 29 tests in 66.178s — OK
```

Damit sind alle betroffenen Browser-Suites grün; D1 ist vom Coding-Agenten
behoben und durch die obigen Läufe bestätigt. Logs außerhalb des Repos:
`/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/final2_*.log`.
