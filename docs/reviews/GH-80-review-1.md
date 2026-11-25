# Independent Review Report — GH-80 (worktree /var/log/custom/vibe-dev/worktrees/vibe-GH-80-mlGDSV, branch feature/korbat/gh-80, HEAD 87c68cb + uncommitted changes)

## Summary

The change set fixes the follow-up gaps left by merged PRs #75/#78/#79 and documents a strategy for the shared `VERIFY_ENV` key. I verified every changed test expectation against the current repository state (all asserted-present strings exist, all asserted-absent strings are absent), checked the manifest follow-up structurally, and reviewed the classification of the remaining reported failures. No weakening of the T-I1 or AP8 acceptance intents was found.

**Finding counts:** Critical 0 · High 0 · Medium 0 · Minor 1 · Notes 4

## Acceptance criteria

| Criterion | Status | Location / evidence |
|---|---|---|
| Investigate each reported failure and fix real regressions | PASS | Manifest follow-up (docs/import-manifest.json 1551–1559, 1605–1611, 1926–1929); rename follow-ups (tests/unit/test_ap7_korbat_rules.py 40–51, tests/unit/test_gh76_platform_instructions.py 346–356); SPEC follow-up (tests/unit/test_ap4_korbat_rules.py 77–162); AP8 browser follow-up (tests/browser/test_ap8_checkout_ui.py 353–357, 400–417) |
| Manifest follow-up complete and correct | PASS | bytes 27744 / sha256 58c6a213… for bin/vibe_harness.py; "aenderungen" entry with arbeitspaket/dateien/datum/grund matching sibling format; "stand" 2026-11-25. Supplied `python3 scripts/check-import-manifest.py → OK (71 Dateien)`; I verified the checker itself validates both bytes and sha256 (scripts/check-import-manifest.py 21–26, 121–129) and that docs/* and tests/* are outside the manifest's file scope, so no further entries are due |
| New expectations match current repo state | PASS | SPEC.md: no `## …Git` heading (grep 0 hits), runner-merge statements verbatim at SPEC.md 80–82, out-of-scope + opt-in line at 245; "Strictly Enforced", `gh pr merge --squash --delete-branch`, `git branch -D`, old German line absent. bin/vibe_harness.py 534–535 contains the ownership sentence and all conflict fragments. AGENTS.md:29 names `docs/verification-baselines.md`, file exists, underscore string only in assertNotIn. bin/vibe_github.py:15 still documents GITHUB_AUTO_MERGE |
| No expectation weaker than the replaced acceptance intent | PASS (see Minor 1) | T-I1: the runner-ownership rule moved from SPEC to the English platform instructions per #75/#79; the new ap4 cases assert that content at its new canonical location, and PR-only/opt-in/squash/forbidden-command checks are preserved or strengthened (the old loose substring checks "pr-only"/"auto-merge" are replaced by verbatim statements). AP8: with the session cookie being valid auth per SPEC and the implementation (bin/vibe-web.py 1185–1196: session first, then X-Token; 403 at 1296), the only meaningful check of "requires credentials" is a no-credentials request; `credentials:'omit'` (test line 408) plus the unchanged `status >= 400 or not ok` and no-directory assertions (416–417) verify the rejection. Session-cookie auth itself has dedicated coverage in tests/unit/test_ap13_web_access.py |
| Remaining failures classified as environment/timing, not product regression | PASS (see Note 4) | ap9/gh56/gh67: Playwright timeouts under nightly load, deterministic local passes (supplied). test_setup_vibe / test_b6_pi_runner_events: "unknown" error class, 3× green locally, not reproducible (supplied). The strategy section in docs/verification-baselines.md correctly describes real engine mechanics: `--env`/VERIFY_ENV and local `.vibe/verify-baseline` precedence exist in scripts/verify_engine.py (76–95, 745–755, 847), so the proposal is implementable without code changes |
| Strategy for the shared environment key | PASS | docs/verification-baselines.md, new section "Environments and locations": one label per execution location, local baseline for the second location, no second-location signatures in the committed baseline, location-independent test advice — consistent with the engine's actual behavior |
| No unrelated changes / scope creep | PASS | Full `git diff HEAD` covers exactly the 6 tracked files below; no production code was touched (correct: all failures were test/manifest drift or environment). Test counts match the supplied focused runs (ap7: 6 methods, gh76: 9, ap4: 7) |

## Findings

**Minor (suggestion, non-blocking):**
1. `tests/browser/test_ap8_checkout_ui.py:376–377` — the test docstring still says "nur mit gültigem Dashboard-Token", but since a session cookie is valid auth per SPEC, the without-credentials case now verifies the authentication requirement, not the X-Token specifically. Suggest rewording the docstring to "nur mit gültiger Anmeldung (Token oder Session)" to avoid future confusion. Not required.

**Notes:**
2. The described change set (5 files) is actually 6 tracked files: `docs/verification-baselines.md` (+24, unstaged) carries the environment-key strategy and belongs to this package; the coordinator must include it when staging. Additionally `docs/features/GH-80.md` exists but is untracked (no git history, not in diff) — expected as the delivery record, must also be staged.
3. I could not independently recompute bin/vibe_harness.py's byte count/SHA-256: the session's permission policy rejected `sha256sum`, `python3`, `openssl`, and non-`diff/log` git commands. The supplied `check-import-manifest.py → OK (71 Dateien)` is accepted as evidence; I verified the checker validates both size and sha256 against the on-disk file, which is exactly what the manifest gate enforces.
4. The two "unknown"-class unit failures (test_setup_vibe, test_b6_pi_runner_events) are classified as load-induced unparsable failures based on supplied local evidence (3× green, not reproducible); residual risk that a real defect hides behind an unparsable failure cannot be excluded from here, and the new docs section's timeout advice is a mitigation proposal, not an applied fix. Acceptable within the ticket's "propose a strategy" scope.
5. Stale baseline entries for `test_ap4_korbat_rules`/`test_ap7_korbat_rules` remain in tests/verify-baseline.json for modules that now pass — harmless (tolerance entries only mask matching signatures), but they could be pruned at the next baseline review.

## Reviewed change set
- docs/import-manifest.json, docs/verification-baselines.md, tests/browser/test_ap8_checkout_ui.py, tests/unit/test_ap4_korbat_rules.py, tests/unit/test_ap7_korbat_rules.py, tests/unit/test_gh76_platform_instructions.py (all uncommitted vs 87c68cb; all inspected via `git diff HEAD`) plus untracked docs/features/GH-80.md.
- Limits: no tests or checks were run by this reviewer (read-only role and permission restrictions); runtime evidence (full verify exit 0 / baseline_ok=1, focused green runs, manifest checker OK) is supplied check output, not independently reproduced.

Post-review edit (orchestrator, wording only): applied Minor 1 — docstring of `test_the_clone_api_creates_the_project_and_requires_the_token` reworded to "nur mit gültiger Anmeldung (Token oder Session)"; no behavior change. Focused module run and full verify refreshed afterwards.

Verdict: PASS
