# Focused Re-Review — Work Package GH-128 (round 2)

**Work package:** GH-128 — GitHub issue sync button placement under the project Work section.
**Worktree / branch / start commit:** `/home/vibe/vibe-logs/worktrees/vibe-GH-128-bZXd9N`, `feature/m0p/gh-128`, `563fa4b`.
**Mode:** read-only re-review; no edits, no commits, no mutating checks performed by me.

## Corrections verified (read-only)

The round-1 Medium finding (F1 — missing enabled-state visibility assertion for the hero issues-sync button) was addressed by the tester in test files only, production code unchanged. I re-read the current sources and confirmed the corrections are present and correctly formed:

1. `tests/browser/test_project_ui.py` — `GithubParityTest.test_issues_sync_sits_in_hero_actions_on_the_work_tab` (~lines 1489–1494): after the presence/position checks, now performs `hook = hero.locator("[data-nv-action='issues-sync']")`, `hook.wait_for(state="visible", timeout=20000)`, and `self.assertTrue(hook.is_visible(), "Der Sync-Button ist im Header nicht sichtbar")`. The negative-phase visibility handling in `test_issues_sync_button_requires_github_feature` (~1516–1519) remains intact.
2. `tests/browser/test_project_ui.py` — enabled phase of `test_issues_sync_button_requires_project_opt_in` (~lines 1550–1554): after enabling the project opt-in and re-opening the Work tab, now performs `hook.wait_for(state="visible", timeout=20000)` and `self.assertTrue(hook.is_visible(), ...)` before the clean-page teardown; the negative gating assertion is unchanged.
3. `tests/browser/test_tickets_ui.py` — enabled phase of `test_issues_sync_is_a_single_hero_action_and_settings_keep_opt_in` (~lines 585–590): after the enabled-state wait/count checks, now performs the visible wait + `assertTrue(hook.is_visible(), ...)`; the pre-existing positive visibility wait in `test_issues_sync_pulls_open_issues_into_the_store` was confirmed present (~line 1573).
4. `tests/unit/test_github_issues.py` — `SurfaceStructureTest.test_nova_hero_sync_posts_issues_sync_and_refreshes` (~lines 2983–2995): now asserts via regex that the hero region couples the button to `NV.feature('github')` and that the un-hide wiring (`issuesSync.hidden = !( … issues_enabled … )` / equivalent `removeAttribute('hidden')` form) exists.

The corrected assertions match the intended F1 remediation precisely and are consistent with the production implementation (hero button creation at `bin/web/nova-project.js:2324–2336`, un-hide at `:2436–2438`).

## Evidence assessment for the final state

- **Focused rerun (supplied):** unit run → `Ran 234, FAILED (8)`, exactly the known pre-existing 5× `NovaIssuesSurfaceTest` + 3× `NovaWaitingSurfaceTest`; all GH-128 cases passed. Browser run → `Ran 218, FAILED (19, errors=5)`, exactly the known pre-existing set; all GH-128 cases including the new visibility assertions passed. `bash scripts/verify.sh quick` → Exit 0. These results are consistent with the corrections and with the pre-existing baseline.
- **Full acceptance (supplied):** `bash scripts/verify.sh full` unflagged → Exit 7 (2800 tests, 64/79 modules, 15 failed; three signatures flagged new, twelve accepted by baseline). Control run in a clean detached worktree at `563fa4b` with the same project env and isolated temp HOME/runtime → Exit 7 (2799 tests, 62/79 modules, 17 failed; the three signatures identical; two control-only module failures attributable to the absent delivery record in the control worktree). Conclusion: no failure introduced by GH-128; the flagged signatures are pre-existing/environmental.
- **Minor follow-up:** living docs and `docs/features/GH-128.md` now state that the hero row is shared by all project tabs; delivery record now carries the full-run and control evidence.

## Findings

- Round-1 Medium F1 (missing enabled-state visibility assertion): **resolved** — corrections verified present at the cited locations; focused re-run evidence shows all GH-128 cases green.
- No new Critical, High, or Medium findings were raised during this focused re-read.
- Minor documentation/wording follow-ups raised in round 1: **resolved** per the coordinator's note.

## Verdict

No blocking findings remain; the round-1 Medium was fixed and re-verified, no GH-128-introduced regression was found, and the final full-run control evidence supports this.

Verdict: PASS
