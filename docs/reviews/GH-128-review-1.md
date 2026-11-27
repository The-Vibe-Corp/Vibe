# Independent Review — Work Package GH-128 (round 1)

**Work package:** GH-128 — "Github Issue Sync button should be placed under the project's 'Work' section"
**Branch / worktree:** `feature/m0p/gh-128` in `/home/vibe/vibe-logs/worktrees/vibe-GH-128-bZXd9N`, start commit `563fa4b`, working tree (uncommitted changes).
**Role:** independent read-only reviewer (no edits, no commits, no checks that mutate state).

## Short summary

The change set moves the single GitHub issues-sync action (`data-nv-action="issues-sync"`) from the Git & GitHub settings section (`nvpGithubSection`) into the project hero top-actions row (`[data-nv-hero] .nv-hero-actions`), creates it only when `NV.feature('github')` is on, starts it hidden, and un-hides it after `/api/project` loads only when `data.github.issues_enabled` is true; on success it posts `{action: 'issues.sync'}` via `nvpPost` and calls `NV.render()`.

Static inspection of all named files confirms the implementation, the backend opt-in wiring (`bin/vibe_github.py` config/status, `bin/vibe-web.py` `/api/github` `issues.sync`), the test sources, the documentation, the import-manifest entry and the Trilium note (`AKxiSAXzqgYU`, parent `Features`/`IjRpjYJTtqam`). No Critical or High production defect was found in the change itself.

## Finding counts by severity

- Critical: 0
- High: 0
- Medium: 1
- Minor: 2 (optional suggestions)

## Acceptance criteria — status, location, evidence

1. **Sync button visible on Work tab next to other top buttons** — PASS (with a test-evidence gap, see Medium finding). Implementation: `bin/web/nova-project.js` hero builder (`heroActions`, lines ~2291–2336; un-hide at lines ~2436–2438). Browser tests: `tests/browser/test_project_ui.py` → `GithubParityTest.test_issues_sync_sits_in_hero_actions_on_the_work_tab` (~lines 1455–1493) and `test_issues_sync_button_requires_project_opt_in` (~1516–1543); `tests/browser/test_tickets_ui.py` → `test_issues_sync_is_a_single_hero_action_and_settings_keep_opt_in` (~537–589). Unit: `tests/unit/test_github_issues.py` → `test_github_card_keeps_issues_fields_but_no_sync_button` (~1872–1903).
2. **Exactly one hook, no settings duplicate, no resurrection of `nv-work-actions`** — PASS. Source: exactly one `issues-sync` occurrence in `bin/web/nova-project.js` (line 2325, hero button); none in the `nvpGithubSection` source region; no `nv-work-actions`/`div.nv-work-actions` anywhere under `bin/web` (grep clean). Tests: unit asserts `self.nova.count("issues-sync") == 1`, hero contains `'issues-sync'`, github section does not; browser asserts settings section count 0, hero count 1, work panel count 0.
3. **Gated by GitHub feature + project opt-in** — PASS. Implementation: `NV.feature('github') ? nvpButton(...) : null`, `hidden` until load, then `issuesSync.hidden = !(data.github && data.github.issues_enabled)`. Browser tests cover feature-off (`test_issues_sync_button_requires_github_feature`) and opt-in-off/on (`test_issues_sync_button_requires_project_opt_in`). Backend opt-in path unchanged and consistent.
4. **Click still posts `issues.sync` and refreshes tickets** — PASS. Handler: `nvpPost(name, '/api/github', {action: 'issues.sync'}, 'Issues synchronisieren', token).then(... → NV.render())`. Unit asserts regex `action\s*:\s*['\"]issues\.sync['\"]` and `NV.render\(\)`; browser `test_issues_sync_pulls_open_issues_into_the_store` clicks the hero hook and waits for GH-7/GH-8 in the store.
5. **Classic UI/backend unchanged** — PASS (evidence-based). Unit `test_classic_issues_section_drops_load_import_and_filter` (in `tests/unit/test_github_issues.py`, passing in the GREEN run) asserts the classic source keeps `Issues synchronisieren` + `action: 'issues.sync'` and drops `issues`/`import`. Backend `/api/github` `issues.sync` handler was inspected and unchanged by the change set per the task description; a live `git diff` re-run was not possible in this session (see limits).
6. **Tests are real assertions, red before fix and green after for GH-128 cases** — PASS. RED output ("'issues-sync' not found in hero") matches the pre-fix source state and the intended assertion; GREEN run shows all GH-128 cases passing, with only the known pre-existing failures (5× `NovaIssuesSurfaceTest`, 3× `NovaWaitingSurfaceTest`) remaining. Supplied check output only — not independently re-run here.
7. **Docs accurate** — PASS for content reviewed (living docs `docs/features/current/github.md`, `ui-shell.md`, `work-packages.md`; delivery record `docs/features/GH-128.md`; index entries; Trilium note). Delivery record still lacks final full-run and review sections (coordinator intends to add) — Minor finding.
8. **Import manifest consistent** — PASS (supplied: `python3 scripts/check-import-manifest.py` → OK, 71 files match; GH-128 entry with refreshed bytes/SHA-256 for `bin/web/nova-project.js` present in `docs/import-manifest.json`).

## Findings

### Required fix (Medium — missing required verification evidence)

- **Finding F1 (Medium):** The primary happy-path placement tests for GH-128 do not assert the *enabled-state visibility* of the hero sync button; they assert element count and DOM position.
  - Location: `tests/browser/test_project_ui.py`, `GithubParityTest.test_issues_sync_sits_in_hero_actions_on_the_work_tab` (~lines 1455–1493, specifically the `wait_until(...count() == 1)` at ~1469–1473 and neighbour/position assertions at ~1474–1488) and the opt-in-enabled phase of `test_issues_sync_button_requires_project_opt_in` (~1516–1543, after `enable_issue_sync_env()` the test waits for count 1 but does not assert visibility); mirrored in `tests/browser/test_tickets_ui.py` (~574–589).
  - Consequence: the test docstring says the button "steht sichtbar" (is visible), but the assertions check count/position only; a button that stayed permanently hidden after the load would pass these tests. The enabled-path visibility is only indirectly covered (click test waits for visible before clicking).
  - Recommended correction: assert positive-state visibility (e.g., `is_visible()` / Playwright visibility wait) in the enabled path of the placement test, and assert the un-hide wiring source (e.g., the `issuesSync.hidden = !(data.github && data.github.issues_enabled)` line) in the unit-level hero test.

### Optional suggestions (Minor)

- `docs/features/GH-128.md` delivery record is still incomplete at review time (no final full-run section, no review section, no commit hash / post-review edit record), although the coordinator intends to add the final full-run and review sections.
- Living docs phrase the button as Work-tab-scoped ("above the Work board"); the implementation places it in the app-wide hero row rendered on all project tabs. Doc precision only, design decision accepted.

## Verification limits

- The `shell` tool was denied in this review session, so no Git diff/status commands, test runs, or check executions were performed by me. The change set was assessed from the task-provided file list plus direct read-only inspection; live re-demonstration of the RED→GREEN sequence was not possible here.
- `bash scripts/verify.sh full` (unflagged) was still running at review time; its result had not been received.

## Verdict

No blocking production defect was found; one Medium verification-evidence finding remains open and, per the project's review rules (PASS requires no Critical, High, or Medium finding), the package verdict is:

Verdict: CHANGES REQUIRED
