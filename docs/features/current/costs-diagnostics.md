# Costs, environment, and diagnostics

Status: current as of 2026-11-26 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

Vibe reports token usage and cost persisted on work packages. It also exposes
resolved paths and environment checks.

## Costs

- `vibe costs [project]` shows sessions, input tokens, cached input, output
  tokens, and cost per package and as a total. Without a project it shows one
  row per project. The view is read-only and makes no model calls (`F12`).
- The source of the overview is the persisted `costs` record on each work
  package in `<project>/.vibe/tickets.json`; it no longer depends on live
  harness sessions. Usage of every session that ran for a package is summed
  into that package, and the per-session entries are overwritten, not added,
  when a package is processed again (GH-99).
- On successful package completion, usage is read from the opencode database
  (opened read-only, primary plus mounted/sandbox databases) and flushed to the
  package before its session assignments are removed. Pause, abort and failed
  runs do not flush or clean up. Migration adopts only unambiguous legacy
  assignments; unmapped legacy sessions are reported by `vibe sessions migrate`
  and are not guessed into a package (GH-99).
- Prices are per 1 million tokens in EUR in the CLI. Precedence is project user
  prices, global user prices, system prices, then the catalog's free/unknown
  classification. Unknown prices are shown explicitly and counted as 0.
- Project user prices live in `<install>/costs.json`, global user prices in
  `<state>/global-prices.json`, and system prices in `<install>/prices.json`.
  The dashboard under `Auswertungen → Kosten` edits prices and can display USD
  using the configured rate; the CLI reports EUR.
- The Nova cost overview (`Auswertungen → Kosten`) shows one compact,
  single-line row per project; long names are truncated with a full-name
  tooltip and narrow viewports scroll horizontally (GH-114).
- An expanded project shows a monthly summary card with labelled fields for
  sessions, input, cached input, output and cost. Token counts and monetary
  values follow the active UI locale (`de-DE` or `en-US`); costs keep four
  decimals and the configured currency symbol (GH-114).
- The project price editor lists every model used in the project, including
  subagent models from `/api/project-agents` (`general`, `explore`). One row
  per model shows agent-role badges and existing prices. Price fields are
  locale-formatted currency inputs; German and English formats, currency
  symbols/codes and non-breaking spaces are accepted, negative/invalid/empty
  input is rejected without saving, and USD entries are converted back to the
  stored EUR base price (GH-114).
- Runtime behavior against unusual or unreadable session schemas was not
  verified here beyond the fallbacks in the code path.

## Paths and environment

- `vibe paths [prod|dev] [--json]` prints the active profile, source,
  workspace, installation, runtime, state, configuration, agent directory,
  container, and the dashboard/opencode URLs. It resolves but changes nothing.
- `vibe doctor` reports the container, workspace writability, required tools,
  the selected harness and its version, `/dev/kvm`, `ANDROID_HOME`, acceptance
  files, configured agent roles, the model catalog, and free disk space.

## Entry points

- CLI: `vibe costs`, `vibe paths`, `vibe doctor`.
- HTTP: `/api/costs` for the cost view and price edits.
- Files: `<project>/.vibe/tickets.json` (persisted package costs),
  `<install>/costs.json`, `<install>/prices.json`,
  `<state>/global-prices.json`.

## Records

- [B1](../B1.md) — cost table refreshes after each package
- [F12](../F12.md) — cost calculation per package and project
- [GH-99](../GH-99.md) — persisted per-package costs and session ownership
- [GH-114](../GH-114.md) — compact overview, monthly summary, all-model price entry
