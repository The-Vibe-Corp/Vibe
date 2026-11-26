## Final independent review report — GH-101 (worktree /home/vibe/vibe-logs/worktrees/vibe-GH-101-cycYe8, change set vs. start commit abc9f94e6a356e36bfa7c63fa26e9ad2fe48824a)

### Summary and findings by severity

The final change set for GH-101 (production: `bin/vibe`, `bin/vibe-web.py`, `bin/web/nova-settings.js`, `bin/web/nova-project.js`, `bin/web/nova.css`, `bin/web/i18n.js`; docs: `docs/import-manifest.json`, `docs/trilium-index.md`, `docs/features/current/agents-models.md`, new `docs/features/GH-101.md`; tester-owned tests under `tests/unit/` and `tests/browser/`) was inspected read-only against start commit `abc9f94e6a356e36bfa7c63fa26e9ad2fe48824a`.

Findings: Critical 0, High 0, Medium 0 outstanding, Minor 2 observations. No security, data-integrity, or behavioral defect was confirmed in the inspected final state. No blockers.

### Acceptance criteria — status and evidence

1. **Always show global AGENTS.md when section opens; compact project selection** — **PASS**.
   - `bin/web/nova-settings.js:392-427` (`fillGlobalAgents`, `drawProjects` render one `select[data-nv-agents-project-select]` with a global option; `selected` reset to `''` at `:395`, `:637`).
   - `bin/web/nova-settings.js:586-615` (`resetToGlobal` via popstate; section re-entry resets selection).
   - Browser evidence: `tests/browser/test_settings_ui.py:5220-5250` (defaults to global after project selection) and `:5253-5287` (no per-project rows; section height does not grow).

2. **Sidebar editor: exactly one editable field, full width, resize, project-mode global preview** — **PASS**.
   - `bin/web/nova-settings.js:459-575` (single `textarea[data-nv-agents-text]`; `details[data-nv-agents-global-preview]` pushed only when `projectName`, directly after the field; `nvMarkdown` renderer; collapsed by default).
   - `bin/web/nova.css:1550-1552` (`.nv-editview-body` min-width 0, overflow; textarea `width:100%; max-width:100%; min-width:0; box-sizing:border-box`).
   - Browser evidence: `tests/browser/test_settings_ui.py:5289-5323+` (exactly one textarea, no before/after fields, width >= 0.9 parent, no horizontal overflow).

3. **Backup/restore scoped to selected file; project backups in project dir** — **PASS**.
   - `bin/vibe:2014-2061` (`agents_file_backup_dir` -> `<project>/.vibe/agents-backups`; `agents_file_backup`; name-scoped `agents_file_restore`).
   - `bin/vibe:2092-2148` (global backup dir), `bin/vibe_storage.py:477-484` (realpath containment in `_resolve_backup`), `bin/vibe-web.py:2259-2277, 2292-2337` (confirm-gated restore).
   - Evidence: `tests/unit/test_agents_md.py:583-648, 815-870` (project-local dir, exact-name restore, cross-scope/foreign rejection).

4. **Remove managed-block support from UI and logic** — **PASS (with evaluated deviation)**.
   - Backend: no marker logic; `agents_file_save` writes `text` verbatim, legacy `before`+`after` concat only for frozen classic UI (`bin/vibe:1911-1925`, tests `:224-288`). View returns full `text`, `before`=full text, `after=""`, `managed=null` (`bin/vibe:1887-1909`).
   - Classic UI deviation evaluated and accepted: `bin/web/app.js:599-629` retains legacy labels/UX, but is byte-hash pinned (`tests/unit/test_ui_style_reference.py:26-30`) and hash-frozen (`docs/style.html` SHA `fe915d3c...`, `:22`-`:46`); backend writes legacy payload verbatim; no marker generation/update logic remains. No block is generated or rewritten; legacy bytes preserved.

5. **Styling and verification** — **PASS** (partially re-verified here; full visual suite not re-run in this session).
   - `tests/unit/test_ui_style_reference.py:22-30, 40-60`; `docs/style.html` component rules (`.input/.select/.combobox-input` width 260px at `:63-66`).
   - Supplied verification: `verify.sh quick` exit 0, `verify.sh package` exit 0, `verify.sh full --env pi-aarch64-py3.14-namespaces` exit 0 (BASELINE-OK; unflagged `full` initially exit 7 solely from `.vibe/project.env` `VERIFY_ENV=head_of_vibe` mismatch, resolved via `--env`). Red phase then focused green runs confirmed by tester.

### Blockers

None confirmed.

### Optional findings / minor

- `bin/web/i18n.js:182-193, 1280-1291` retains managed-block UI strings; retained intentionally because the hash-frozen classic UI (`bin/web/app.js:605-627`) still consumes them — consistent, no action required.
- Full visual screenshot verification (`tests.browser.test_new_ui_style_screenshots`) was not re-inspected in this session.

### Verification limits

Read-only inspection only; shell execution was denied during this review, so Git diff and test-suite re-runs could not be performed here. Check outputs quoted were supplied by the tester and are distinguished from this review's own results. Full style/visual screenshot suite and live browser run not re-verified by this reviewer.

### Verdict

Verdict: PASS
