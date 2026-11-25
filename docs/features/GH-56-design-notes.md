# GH-56 — Design-Verträge (Projektansicht „Work")

Status: Umgesetzt und geprüft. Finale Beschreibung in `docs/features/GH-56.md`;
diese Notizen bleiben als Vertragsnachweis aus der Planungsphase erhalten.
Referenz: Ticket `TICKET-GH-56.json`; bestehende Modelle: `bin/web/nova-project.js`,
`bin/web/nova.css`, `bin/web/nova.widgets/editview`.

Hinweis zu GH-82: Die folgenden Abschnitte halten den historischen
GH-56-Planungsstand fest. Seit GH-82 sind nur noch `draft` und `open` manuell
setzbar; `ticket-close`, `package-close`, der `done`-Schnellfilter und das
`draft`-Kontrollkästchen gibt es in der Oberfläche nicht mehr. Maßgeblich ist
`docs/features/current/work-packages.md`.

## Zustandsmodell (Backend, unverändert)

`vibe_tickets.STATES`: `draft`, `open`, `in-progress`, `blocked`, `waiting-merge`, `done`.
Web-Übergänge via `/api/ticket` (historisch `draft|open|in-progress`, seit
GH-82 nur noch `draft|open`).
GitHub-Issues mappen lokal `ready → open` (`vibe_issues._local_state_value`).

## Board-Spalten (Desktop)

| data-nv-col | Spaltenüberschrift         | Ticket-Zustände                     |
|-------------|----------------------------|-------------------------------------|
| draft       | Entwurf                    | `draft`                             |
| ready       | Bereit zur Implementierung | `open` (badged „Ready")             |
| running     | In Umsetzung               | `in-progress`                       |

Tickets mit `blocked`/`waiting-merge` erscheinen zusätzlich auf der Ready-Karte
(Sichtbarkeit behalten). `done` bleibt standardmäßig verborgen
(„Erledigte anzeigen").

`nvpColOfState(state)` liefert die Spalte: `draft`→draft; `open`/`blocked`/
`waiting-merge`→ready; `in-progress`→running; `done`→`ready` (hidden, wenn
hideDone).

## DOM-Verträge (Karten & Board)

```
div[data-nv-board]
└── article[data-nv-col="draft|ready|running"]
    ├── div[data-nv-col-head]        → h3.nv-col-title + span[data-nv-col-count]
    ├── div[data-nv-col-cards]       → article[data-nv-ticket="<id>"] (Karten)
    └── div[data-nv-col-empty]       → „Leere Spalte"-Hinweis
```

Karten: weiters `article[data-nv-ticket]` — Titel `.nv-ticket-title` (mit
`.nv-ticket-head`), Status-Pille `.nv-pill` (Trennung Badge/linke Kante wie
bestehend), Badges `span[data-nv-prio-badge]`, `data-nv-state` auf dem Card,
`data-nv-session` = Session-ID für Resume.

### Karten-Actions (data-nv-action)

- `ticket-details` (Details → Änderung via Kontext-Panel, wie F34 bestanden)
- `ticket-resume` (Resume; sichtbar für `in-progress`/`blocked`/`waiting-merge`)
- `priority-up`/`priority-down` (auf Karten in Spalten ↑/↓ per Tile, Ohne
  DnD wird die Vertikale ordentlich Keyboard-steuerbar)

### Drag-and-Drop (board-only)

HTML5 Drag: `draggable="true"` auf `article[data-nv-ticket]`.
`dragstart` → insert tracker + Ghost (`div[data-nv-board-ghost]`,
`document.body`, position fixed, opacity ~0.9); `dragover` → Drop-Zielmarker
(`div[data-nv-drop-marker]`); `drop` → Ziele spalte:

- `draft → ready` / `ready → draft`: `POST /api/ticket {action:"state"}`
  (draft↔open). Optimistisch + Rollback auf Fehler.
- gleiche Spalte: Ordnung via `/api/priority` speichern (vertikal).

## Priorisierungsschritt (nvpPriorityStrip)

`readyOnly`-Modus (Work-View): nur Tickets mit `state=open` Listenreihenfolge.
Speicherung `POST /api/priority {name, action:"set", order}` (Bestand).

## Filter / Suche

Existierende `nvpWireWorkFilters` erweitert: State-Chip-Zeile
`[data-nv-work-states]` mit `button[data-nv-work-state="draft|ready|running|done"]`,
`aria-pressed`-Marker; Board + Liste reagieren identisch über `[hidden]`.

## Ticket-Editor (Sidebar)

Reißverschluss: `nvpOpenTicketForm` → neu als Editor in `NV.editView`
(GH-57-Aside rechts, volle Höhe, sessionStorage-Breite).

- Hooks: `aside[data-nv-editview][data-nv-ticket-editor]`,
  `[data-nv-field="title"|"description"|"state"|"id"|"draft"]`,
  `button[data-nv-action="ticket-save"|"ticket-cancel"|"ticket-close"]`.
- **Standardwert des Zustands: `draft`**. `WEB_TICKET_STATES` bleibt
  unverändert — die Erweiterung um `done` wurde verworfen, weil sie den
  GH-48-Schutz für Läufer-/GitHub-Zustände aufgeweicht hätte.
- Speicher: `POST /api/ticket {action:"add"}`, `close`: `{action:"close",
  confirm:true}` — native `window.confirm`-Rückfrage plus serverseitiges
  Flag als doppelte Absicherung. Finale Begründung in `docs/features/GH-56.md`.
- „Kopieren als neu" (`data-nv-action="ticket-copy"`) bei `done`-Karten →
  `POST /api/ticket {action:"add", state:"draft"}` mit belegtem Titel/Beschreibung.

## Mobile

`matchMedia('(min-width: 769px)')` → Board; sonst `div[data-nv-work-list]`.
Priority-Strip nur Ready. Editview ist auf ≤768px Vollbild (CSS Bestand).

## i18n

Neue Deutschen Quellschlüssel werden in `VIBE_I18N.extend({en, de})`
(nova-project.js, Bestand).
