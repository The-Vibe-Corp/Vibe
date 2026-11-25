# Feature documentation

Living feature documentation describes the current behavior of each feature. It is written in English and kept under [`current/`](current/). The ticket records in this directory (`<ID>.md`) are delivery records for individual work packages: most are in German and historical, and each keeps the ticket ID and title, what changed, the verification evidence, and links to the relevant living documentation. [`SPEC.md`](../../SPEC.md) remains the authority on product requirements.

## How to read this directory

| Convention | Meaning |
| --- | --- |
| `current/<name>.md` | Living documentation of the current behavior of a feature group, in English. |
| `<ID>.md` | Delivery record for one work package: ID and title, change, evidence, links. |
| Descriptive suffix, e.g. `B1-ticketlogik.md` | A reused ticket ID documented under a distinct name because the plain `<ID>.md` belongs to an older package. |
| `AP*-Korbat.md` series | A later feedback wave that reuses the AP numbers; distinguish by title and content. |
| Non-ticket slugs, e.g. `verify-tmux-isolation.md` | Records without a numeric ticket ID. |

Language note: historical records are mostly German. New and living content is written in English.

## Features

### Projects and development directories

Living documentation: [Projects and development directories](current/projects.md)

- [AP15.md](AP15.md) — fast project view via cached scrypt derivation
- [F13.md](F13.md) — project detail restructured into tabs
- [F14.md](F14.md) — project type "Rebuild"
- [F2.md](F2.md) — edit feedback and control output
- [F9.md](F9.md) — project assistant for new-project setup
- [V-008.md](V-008.md) — regression coverage for project administration and templates

### Work packages, feedback, and ticket store

Living documentation: [Work packages, feedback, and ticket store](current/work-packages.md)

- [AP11.md](AP11.md) — configurable prioritization order for work items
- [B1-ticketlogik.md](B1-ticketlogik.md) — ticket logic: one type field, calm editor
- [F1.md](F1.md) — feedback capture reduced to title and description
- [F15.md](F15.md) — create work packages and bugs in UI
- [F23.md](F23.md) — automatic work-package ID assignment
- [F29.md](F29.md) — feedback on AP11 prioritization
- [F8.md](F8.md) — hide and protect completed feedback items
- [GH-48.md](GH-48.md) — unified machine-readable ticket store
- [V-009.md](V-009.md) — stabilize ticket and feedback processing
- [worknotes-nachweis-sync.md](worknotes-nachweis-sync.md) — write ticket evidence back without versioning

### Runner and package flow

Living documentation: [Runner and package flow](current/runner.md)

- [AP05.md](AP05.md) — clean package handling
- [AP10.md](AP10.md) — gate settings and deliberate continuation
- [AP4-Korbat.md](AP4-Korbat.md) — rework package completion for GitHub projects
- [B3-wartet-auf-merge.md](B3-wartet-auf-merge.md) — merged package stuck as waiting for merge
- [B5.md](B5.md) — package close workflow on merge conflict
- [B6-statusmarken.md](B6-statusmarken.md) — status markers only at status positions
- [B9.md](B9.md) — self-repair blocked packages
- [F22.md](F22.md) — preflight questions instead of abort
- [F27.md](F27.md) — resume interrupted run despite uncommitted changes
- [F4.md](F4.md) — stop after current package
- [GH-58.md](GH-58.md) — autonomous mode setting ignored
- [V-022.md](V-022.md) — git order as general project rule
- [V-023.md](V-023.md) — completion gate recognizes already merged packages
- [V-027.md](V-027.md) — explicit global limit behavior

### Agents, models, and profiles

Living documentation: [Agents, models, and profiles](current/agents-models.md)

- [AP01.md](AP01.md) — guidelines for coding agents
- [AP02.md](AP02.md) — mandatory test agent
- [AP03.md](AP03.md) — agent management revision
- [AP04.md](AP04.md) — interchangeable coding harness and Pi
- [AP17.md](AP17.md) — additional agent roles
- [AP2-Korbat.md](AP2-Korbat.md) — opencode v2 permission syntax and subagents
- [B2.md](B2.md) — AGENTS.md available in package
- [B4.md](B4.md) — Pi harness agent-directory sandbox error
- [F17.md](F17.md) — per-project agent management
- [F20.md](F20.md) — Pi integration in dashboard and app
- [F21.md](F21.md) — release UI-configured agents for a run
- [F26.md](F26.md) — OpenCode integration accepts newer versions
- [F31.md](F31.md) — view and edit AGENTS.md free sections
- [GH-76.md](GH-76.md) — hide mandatory template AGENTS.md section
- [V-010.md](V-010.md) — complete agent management
- [V-011.md](V-011.md) — clean and document model catalog
- [V-025.md](V-025.md) — invalid start agent in project selection

### MCP servers

Living documentation: [MCP servers](current/mcp.md)

- [V-007.md](V-007.md) — opencode compatibility adapter
- [V-013.md](V-013.md) — lossless MCP configuration editing
- [V-014.md](V-014.md) — robust bounded MCP connection tests

### Agent runs and output

Living documentation: [Agent runs and output](current/runs-output.md)

- [AP14.md](AP14.md) — output view complete rework
- [AP16.md](AP16.md) — syntax highlighting in agent output
- [AP19.md](AP19.md) — session management
- [AP20.md](AP20.md) — output UI improvements
- [B11.md](B11.md) — rebuilt output view, stop ends agent
- [B12.md](B12.md) — subagents invisible in output
- [B13.md](B13.md) — send instruction error, private opencode server
- [B14.md](B14.md) — live subagent output
- [B20.md](B20.md) — scrollable preview, autoscroll, focus toggles
- [B3.md](B3.md) — send message error, automatic password file
- [B6.md](B6.md) — F24 output features do not work correctly
- [F10.md](F10.md) — agent run stops automatically
- [F16.md](F16.md) — answer agent follow-up questions
- [F19.md](F19.md) — output view highlighting, control, subagents
- [F24.md](F24.md) — output view active agent and tabs
- [F25.md](F25.md) — session continuation on retry
- [F30.md](F30.md) — live, large, resizable subagent view
- [F32.md](F32.md) — subagent parallelism as opt-in
- [V-015.md](V-015.md) — decouple agent runs and project checks
- [V-016.md](V-016.md) — test dashboard and opencode lifecycles separately
- [V-024.md](V-024.md) — detect and clean orphan run entries
- [V-026.md](V-026.md) — protect runs from foreign tmux cleanup

### Verification and checks

Living documentation: [Verification and checks](current/verification.md)

- [AP5-Korbat.md](AP5-Korbat.md) — clean bugs and artifacts, improve checks
- [AP6-Korbat.md](AP6-Korbat.md) — unit test hygiene cleanup
- [AP7-Korbat.md](AP7-Korbat.md) — rework verify.sh logic
- [B17.md](B17.md) — development and verification must not touch running instance
- [GH-46.md](GH-46.md) — fix new testing logic
- [GH-80.md](GH-80.md) — integration branch test regression failure
- [V-001.md](V-001.md) — capture and secure unchanged inventory
- [V-002.md](V-002.md) — secure development and test environment
- [verify-tmux-isolation.md](verify-tmux-isolation.md) — verification leaves caller's tmux server untouched

### Security, permissions, and sandbox

Living documentation: [Security, permissions, and sandbox](current/security-sandbox.md)

- [AP1.md](AP1.md) — opencode-go sandbox and private server rights
- [AP13.md](AP13.md) — reach vibe locally over network
- [AP18.md](AP18.md) — set WebUI password via CLI
- [AP23.md](AP23.md) — key management
- [B7-subagent-permissions.md](B7-subagent-permissions.md) — subagent rights in template rendering
- [F3.md](F3.md) — dynamic write permissions per project
- [F7.md](F7.md) — sandbox for shell and build tools
- [V-003.md](V-003.md) — secure process calls and inputs
- [V-004.md](V-004.md) — secure web API, add health endpoint
- [V-005.md](V-005.md) — atomic file access and safe backups
- [fix-opencode-password-env.md](fix-opencode-password-env.md) — inherited password blocked private server

### Installation, update, and release

Living documentation: [Installation, update, and release](current/install-release.md)

- [B4-install-leerer-laufzustand.md](B4-install-leerer-laufzustand.md) — install fails on empty run state
- [F6.md](F6.md) — universal setup process
- [REPO-CLEANUP-GITHUB.md](REPO-CLEANUP-GITHUB.md) — clean repository for GitHub publication
- [V-006.md](V-006.md) — separate source, install, runtime paths
- [V-017.md](V-017.md) — production-ready Bazzite starter
- [V-018.md](V-018.md) — install, update, rollback
- [V-020.md](V-020.md) — browser acceptance, documentation, release base
- [V-021.md](V-021.md) — install completeness and cleanup rules

### GitHub integration

Living documentation: [GitHub integration](current/github.md)

- [AP12.md](AP12.md) — prepare repository for public push
- [AP3-Korbat.md](AP3-Korbat.md) — GitHub issue support for managed projects
- [AP6.md](AP6.md) — prepare for GitHub repository
- [AP8.md](AP8.md) — checkout project from GitHub
- [AP9.md](AP9.md) — per-project token, branch control, merge request
- [B16.md](B16.md) — prepare finished packages as GitHub PRs
- [B7.md](B7.md) — GitHub authentication through UI
- [B8.md](B8.md) — project open blocked by unreachable remote
- [GH-47.md](GH-47.md) — unified bidirectional GitHub issue sync

### Costs, environment, and diagnostics

Living documentation: [Costs, environment, and diagnostics](current/costs-diagnostics.md)

- [B1.md](B1.md) — cost table refreshes after each package
- [F12.md](F12.md) — cost calculation per package and project
- [F18.md](F18.md) — central internet reconnect for several projects
- [F5.md](F5.md) — Fritzbox reconnect in UI

### Dashboard UI shell

Living documentation: [Dashboard UI shell](current/ui-shell.md)

- [AP7.md](AP7.md) — settings UI rebuilt
- [AP21.md](AP21.md) — global language and i18n switcher
- [AP22.md](AP22.md) — new vibe web UI
- [B18.md](B18.md) — harness selectable only when installed
- [F11.md](F11.md) — fewer modal browser dialogs
- [F33.md](F33.md) — work-package UI Nova rework
- [F34.md](F34.md) — UI improvements, contract and plan
- [GH-56.md](GH-56.md) — project work view board and editor
- [GH-56-design-notes.md](GH-56-design-notes.md) — design contracts for work view
- [GH-57.md](GH-57.md) — settings UI rework
- [GH-67.md](GH-67.md) — shared sidebar and work cleanup

### Cross-cutting and internal work

No living documentation yet.

- [AP24.md](AP24.md) — project licence
- [F28.md](F28.md) — pylint improvement round
- [GH-60.md](GH-60.md) — code janitor round
- [GH-68.md](GH-68.md) — codebase-wide janitor analysis
- [V-019.md](V-019.md) — gradual frontend and backend modularization
- [GH-70.md](GH-70.md) — feature documentation index and living docs

## Reused ticket IDs and naming collisions

- B1, B3, B4, B6, and B7 each have an older closed package in the plain file (`B1.md`, `B3.md`, `B4.md`, `B6.md`, `B7.md`) and a newer package under a descriptive suffix (`B1-ticketlogik.md`, `B3-wartet-auf-merge.md`, `B4-install-leerer-laufzustand.md`, `B6-statusmarken.md`, `B7-subagent-permissions.md`).
- `B1.md` contains three same-ID entries: the original cost-table record (2026-11-07) plus two appended sections — project models (2026-11-20) and ticket logic (2026-11-24, which links to `B1-ticketlogik.md`).
- `AP1.md` (opencode-go sandbox and private server rights) and `AP01.md` (guidelines for coding agents) are different topics sharing a number.
- `AP7.md` exists; there is no `AP07.md`.
- The `AP*-Korbat.md` series documents a later feedback wave reusing the AP numbers; distinguish entries by title and content.
- B10, B15, B19, and V-012 have no record files in this repository.
- `GH-56.md` and `GH-56-design-notes.md` are design contracts for the work view and belong to the same package.

## Verified discrepancies between historical records and current implementation

The following points were checked against the current implementation while building this index. They are recorded as discrepancies, not as current behavior.

- [`AP05.md`](AP05.md) describes a branch pattern `vibe/<name>-<ID>-…`; the current default pattern is `feature/{owner}/{id}` (`bin/vibe_packages.py`, `DEFAULT_PACKAGE_BRANCH_PATTERN`).
- [`AP05.md`](AP05.md) describes the gate as checking TICKETS.md/FEEDBACK.md markers; the current gate reads `TICKET-<ID>.json` evidence against `.vibe/tickets.json` (`bin/vibe_packages.py`, `gate_errors`).
- [`B6-statusmarken.md`](B6-statusmarken.md) describes marker states in TICKETS.md/FEEDBACK.md; states are now fields in `.vibe/tickets.json` (`bin/vibe_tickets.py`, `STATES`).
- [`F9.md`](F9.md) lists TICKETS.md/FEEDBACK.md among the assistant's files; the current `vibe_guide.FILES` is SPEC.md, AGENTS.md, `.vibe/project.env`, and README.md (`bin/vibe_guide.py`).
- [`F13.md`](F13.md) describes four project detail tabs; the current UI has five tabs (overview, work, output, assistant/"Beschreibung", settings; `bin/web/nova-project.js`). `docs/handbuch.md` calls the assistant tab "Assistent"; the current UI label is "Beschreibung".
- [`AP03.md`](AP03.md), [`F17.md`](F17.md), and [`V-010.md`](V-010.md) describe project agent configuration version 2 or 1; the current `PROJECT_AGENTS_VERSION` is 3 (`bin/vibe`).
- Several historical records name `scripts/verify.py` as the verification entry point (for example [`V-002.md`](V-002.md), [`F31.md`](F31.md), and [`verify-tmux-isolation.md`](verify-tmux-isolation.md)); the canonical engine is `scripts/verify_engine.py`, and `verify.py` is a compatibility shim (the split is documented in [`AP7-Korbat.md`](AP7-Korbat.md)).
- [`V-001.md`](V-001.md) states 22 import-manifest entries; the current manifest covers 71 files (`docs/import-manifest.json`, which grew over later tickets).
- SPEC.md requires auditable logs for security-sensitive actions; no dedicated audit-log implementation was located in the current code (`bin/vibe-web.py`). This remains an open discrepancy and is not documented as behavior.

## Related documentation

- [`SPEC.md`](../../SPEC.md) — product scope and binding requirements.
- [`docs/handbuch.md`](../handbuch.md) — UI and CLI operation.
- [`docs/betrieb.md`](../betrieb.md) — paths, processes, diagnostics, installation, and release.
- [`docs/grenzen.md`](../grenzen.md) — known limits and unsupported functions.
- [`docs/compatibility.md`](../compatibility.md) — harness and environment compatibility.
- [`docs/checkliste.md`](../checkliste.md) — acceptance checklist with versions and results.
- [`docs/baseline.md`](../baseline.md) — verification baseline.
- [`docs/abnahme-bazzite.md`](../abnahme-bazzite.md) — documented manual Bazzite check.
- [`docs/verification-baselines.md`](../verification-baselines.md) — baseline exceptions and handling.
- [`docs/trilium-index.md`](../trilium-index.md) — mapping of records to Trilium notes.

This index was created by GH-70. Historical review reports live under [`docs/reviews/`](../reviews/) and are not re-indexed here.
