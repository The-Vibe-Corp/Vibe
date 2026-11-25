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
- Settings use their own responsive navigation with ten sections: global
  AGENTS.md, appearance, access security, features, run behavior, gates,
  models, profiles, MCP servers, and harness (`AP7`, `GH-57`).
- Section actions redraw only their own section. Harness selection reflects
  what is installed: an uninstalled harness is disabled and cannot be saved;
  the persisted `harness.json` remains the displayed state (`B18`).

## Work view

- The project detail has five tabs; the Work tab contains the ticket surface.
  It shows a three-column board on desktop (draft, ready, in progress) and a
  list on mobile, with shared filter and search controls.
- The editor and detail view open in the shared context panel. Status changes,
  prioritization, and drag-and-drop update the ticket store without a full page
  reload. Ticket semantics belong to [Work packages](work-packages.md) (`GH-56`,
  `F33`, `F34`).
- `GH-67` consolidated the shared sidebar and cleaned up the work view: one
  priority strip on mobile, localized labels, and a single card in the DOM.
  The binding design contracts are in the
  [GH-56 design notes](../GH-56-design-notes.md).

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
  [GH-56-design-notes](../GH-56-design-notes.md), [GH-67](../GH-67.md).
- Foundation: [AP22](../AP22.md).
