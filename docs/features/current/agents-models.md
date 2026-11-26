# Agents, models, and profiles

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

## Agent files

- Global agents live in `~/.config/opencode/agents` as Markdown files with a
  YAML frontmatter block (name, description, mode, model, permissions).
- Vibe's project settings manage the global inventory. At runtime opencode
  still honors project-local overrides, so a project file can shadow a global
  agent.
- The structured editor changes only the fields it owns; unknown frontmatter
  fields are preserved. Invalid input is rejected before writing and leaves the
  existing file unchanged.
- Every save writes a backup; `vibe agent backups`/`restore` list and restore them.

### AGENTS.md files

- The settings section always opens on the global AGENTS.md. One compact select switches to
  a project-specific AGENTS.md; selecting a project does not add rows or cards to the page.
- All editing happens in the sidebar in a single full-text field that fills the sidebar
  width and follows resize. In project mode a collapsed, read-only, formatted-Markdown
  preview of the global file is available directly below the field; it is absent in global
  mode.
- Backups and restores are scoped to the selected file. Project backups live in
  `<project>/.vibe/agents-backups` and restore requires an explicit backup name, so a
  backup from another project or from the global store cannot be applied here.
- Managed blocks no longer exist in the UI or backend. An existing legacy block is ordinary
  file content and is preserved byte-identically; nothing is generated, updated or deleted.
  The frozen classic UI reads inert compatibility fields from the view.

## Roles

Roles are stored under `rollen` in `<state>/profiles.json` and map an agent to
a role such as coder, reviewer, tester, or vibe. At most one agent has the
`vibe` role; assigning it elsewhere removes the old holder, and the last vibe
agent cannot be demoted.

## Model catalog

- `data/models.json` uses schema 2. `validate()` requires a source and date for
  every non-unknown value and marks prices older than 90 days as stale.
- The live model list comes from the active harness (`opencode models` or
  `pi --list-models`); it determines what can actually be selected.
- `<state>/models-cache.json` caches that list and is refreshed only through
  `POST /api/agents` with `action=refresh_models`.

## Profiles

- `default`, `free`, `mid`, and `high` are protected standard profiles; user
  profiles can be added. Profiles assign models per role.
- Applying a profile resolves each role through the chain: profile value →
  default role model → model of the vibe agent.
- All resolved models are checked against the live list before the first agent file is written; an empty profile reports nothing as applied.
- The writes are sequential and have no rollback. Prevalidation prevents an
  unknown model, but a later filesystem error can leave earlier agents updated.
  This remains a gap against the spec's transactional-or-reversible rule.

## Harness

- The active harness is stored in `<state>/harness.json`; `VIBE_HARNESS`
  overrides it for one process.
- Supported harnesses are `opencode` and `pi`; opencode is the default when no
  selection exists.

## Platform instructions

GH-76 keeps the platform text as a hidden constant in `bin/vibe_harness.py`.
It is written as `platform_instructions.md` into the state directory and passed
to opencode through `OPENCODE_CONFIG_CONTENT`. The former `GENERAL_RULES`
block was removed from projects and templates.

## Discrepancy note

AP03.md, F17.md, and V-010.md describe agent configuration version 2 or 1; the
current `PROJECT_AGENTS_VERSION` is 3.

## Entry points

- CLI: `vibe agents`, `vibe agent new|edit|show|rm|backups|restore`,
  `vibe models`, `vibe profile list|use`, `vibe harness status|list|use|setup`.
- HTTP: `/api/agents`, `/api/profiles`, `/api/harness`.

## Records

- [AP01](../AP01.md) — coding-agent guidelines; [AP02](../AP02.md) — mandatory test agent
- [AP03](../AP03.md) — agent management revision; [AP04](../AP04.md) — interchangeable harness
- [AP17](../AP17.md) — additional roles; [AP2-Korbat](../AP2-Korbat.md) — opencode v2 permissions
- [B2](../B2.md) — AGENTS.md in the package; [B4](../B4.md) — Pi agent directory
- [F17](../F17.md) — per-project agents; [F20](../F20.md) — Pi in the dashboard
- [F21](../F21.md) — release UI agents; [F26](../F26.md) — no version blocking
- [F31](../F31.md) — edit free AGENTS.md parts; [GH-76](../GH-76.md) — hidden platform instructions
- [GH-101](../GH-101.md) — AGENTS.md settings rework, scoped backups, managed block removed
- [V-010](../V-010.md) — complete agent management; [V-011](../V-011.md) — evidence-based catalog
- [V-025](../V-025.md) — invalid start agent in the project selection
