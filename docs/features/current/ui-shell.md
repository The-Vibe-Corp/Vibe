# Dashboard UI shell

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

The dashboard is a single-page app rendered by `bin/web/nova-*.js`. Its shell
keeps global navigation, contextual panels, notifications, and answers visible
without a static sidebar.

## Header and navigation

- The header has five areas: Start, Agenten, Aktivität, Auswertungen, and
  Einstellungen. On narrow screens a menu button opens the same navigation.
- There is no permanent sidebar. Context, editing, prices, and the question
  mailbox open in a situational right-side panel. The shared controller
  `NV.sidebar` closes a panel with ×, `Escape`, or a click on its background.
- Dashboard and opencode status are shown in the header. The classic interface
  remains reachable from settings.

## Notifications and questions

- Notifications appear in exactly one place: transient toasts sit under the
  bell, and persistent bell entries survive a reload. Each entry can be closed
  individually; “Alle als gelesen” clears the stored list, and a counter shows
  unread entries.
- Agent questions appear as a banner below the header, a highlighted counter,
  a bell entry, and a mailbox in the side panel. The answer is sent inline and
  removes the question without reloading the page. The question behavior itself
  is documented in [Agent runs and the output view](runs-output.md) (`F16`).

## Language and settings

- The interface is English by default and can be switched globally between
  English and German under Einstellungen → Darstellung. The choice is saved in
  `ui.json` through `/api/language` and applies to the whole interface (`AP21`).
- Settings use their own responsive navigation with nine sections: global
  AGENTS.md, appearance, access security, features, gates, models, profiles,
  MCP servers, and harness (`AP7`, `GH-57`). The former "Run behaviour" section
  and its toggle were removed; legacy `limits.json` files cannot reintroduce
  them or influence runs (GH-99).
- Section actions redraw only their own section. Harness selection reflects
  what is installed: an uninstalled harness is disabled and cannot be saved;
  the persisted `harness.json` remains the displayed state (`B18`).

## Work view

- The project detail has five tabs; the Work tab contains the ticket surface.
  It shows a three-column board on desktop (draft, ready, in progress) and a
  list on mobile, with shared filter and search controls. Completed tickets
  appear in their own grid below it and stay behind the `Show done` toggle;
  users can set only draft/open, while blocked, awaiting-merge, and done belong
  to the runner (`GH-82`, `GH-108`). Native dropdowns share one Nova select
  style.
- Since `GH-108`, the quick filters occupy a row above the search field, which
  uses only its content width instead of the full panel; `Show done` sits
  directly to its right. `Add package`, `Report bug`, and `Give feedback` live
  permanently in the hero row on every tab, while `Check` and `Full
  verification` are reachable through a collapsed `More actions` menu there.
  `Start working` is disabled while a run is active, and the In Progress
  `Continue` button is disabled while a session of the project is running.
- The editor and detail view open in the shared context panel. Status changes,
  prioritization, and drag-and-drop update the ticket store without a full page
  reload. In-progress tickets can be returned to draft or ready from the card,
  by drag-and-drop, or from the detail sidebar (`GH-108`). Ticket descriptions
  render as formatted Markdown in detail view, and ticket form fields use the
  full sidebar width (`GH-108`). Ticket semantics belong to
  [Work packages](work-packages.md) (`GH-56`, `F33`, `F34`).
- The project overview lists sessions grouped under their work package: the
  package and project give orientation, while the technical session ID is
  muted, truncated and equipped with a tooltip containing the full ID (GH-99).
- `GH-67` consolidated the shared sidebar and cleaned up the work view: one
  priority strip on mobile, localized labels, and a single card in the DOM.
  The binding design contracts are in the
  [GH-56 design notes](../GH-56-design-notes.md).
- `GH-115` extends the mobile priority strip to the implementation order: it
  lists every ticket that is not closed and not a draft — `in-progress` first,
  then `open`/Ready, `blocked`, and `waiting-merge` — with priority only
  ordering within a status group. Saved positions remain authoritative; the
  strip no longer shows only Ready tickets.

## Visual style

Since `GH-94`, Nova follows the “Precise Frames × Technical Density” reference stored at [`../style.html`](../style.html): matte light/dark palettes, 1 px frames, radii of 2–6 px, compact control heights, a 4/8/12/16/24/32 px spacing scale, and technical typography (Inter for UI text, JetBrains Mono for technical values). All styling lives in `bin/web/nova.css` and uses `--nv-*` custom properties. Theme and accent selection are unchanged (12 accents, `blue` default, attributes on `html`), and the classic interface keeps its own stylesheet.

The agents list applies the same header alignment to its title, search field
and "New Agent" action, and its cards use a flex column so Edit/Delete stay on a
common bottom line across cards of different content height (`GH-109`; details
in [Agents, models, and profiles](agents-models.md)).

## Verification note

The shell behavior above was checked against `bin/web/nova-core.js`,
`nova-settings.js`, `nova-project.js`, `nova-widgets.js`, and the handbook.
Exact responsive breakpoints and visual styling were not verified here.

## Entry points

- Routes: `#/home`, `#/agents`, `#/activity`, `#/evaluations/<tab>`,
  `#/settings`, `#/project/<name>/<tab>`.
- HTTP: `/api/language`, `/api/security`, `/api/questions`, `/api/ticket`.
- Files: `bin/web/index.html`, `bin/web/nova-*.js`, `bin/web/nova.css`,
  `bin/web/i18n.js`, `ui.json`.

## Records

- Shell and settings: [AP7](../AP7.md), [GH-57](../GH-57.md),
  [B18](../B18.md), [F11](../F11.md).
- Language: [AP21](../AP21.md).
- Work view: [F33](../F33.md), [F34](../F34.md), [GH-56](../GH-56.md),
  [GH-56-design-notes](../GH-56-design-notes.md), [GH-67](../GH-67.md),
  [GH-99](../GH-99.md), [GH-108](../GH-108.md), [GH-115](../GH-115.md).
- Visual style: [GH-94](../GH-94.md), [GH-88](../GH-88.md).
- Foundation: [AP22](../AP22.md).
