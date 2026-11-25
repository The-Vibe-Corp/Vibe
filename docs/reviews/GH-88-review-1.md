# Review — GH-88 “kleine Verbesserungen ui Ausgabe” (round 1)

Independent read-only review of work package GH-88 in worktree `feature/m0p/gh-88`, start commit `b525805`. No files were modified by the reviewer.

## Summary

All four ticket requirements are implemented in the Nova output view. The follow-mode logic, shared responsive card grid, token-based card styling, and removal of the redundant status row were reviewed against the code and the supplied test evidence. No critical, high, or medium findings; three minor documentation wording findings were reported and are optional. Verdict: PASS.

## Scope reviewed

- `bin/web/nova-output.js`: `nvOutFollow()` (per-log `{follow, guard}` state, 24 px threshold, scroll guard released via `requestAnimationFrame`, `write()` snapshotting `wasFollow` and preserving `scrollTop`, `refresh()` on focus/expand), `feedMain()`, `setCardText()`, `setLogLimit()`, `applyFocus()`, `makeCard()`, `pollAgents()`, and the dual-render guard.
- `bin/web/nova.css`: `.nv-out-cards`, `.nv-out-subs { display: contents }`, head/log blocks, disabled slide-in for preview cards, log heights.
- `tests/browser/test_output_ui.py`: new `OutputCardBehaviorTest`, adapted `SubGridTest`, changed wait anchors and run-state read.
- `docs/features/GH-88.md`, `docs/features/README.md`, `docs/features/current/runs-output.md`, `docs/import-manifest.json` GH-88 entry.

## Acceptance criteria

| Requirement | Status | Evidence |
|---|---|---|
| 1. Output stays at a user-selected position; autoscroll resumes at the newest position | PASS | `nvOutFollow()` in `nova-output.js`: scroll threshold, guarded programmatic writes, preserved `scrollTop`, `refresh()` on focus/expand; main and sub logs both use `write()`. Red phase showed uncontrolled jumps before the fix; new browser cases pass after it. |
| 2. Agent/subagent preview cards in a grid for every screen size | PASS | `[data-nv-out-cards]` grid, `.nv-out-subs` uses `display: contents`; test covers 1400/900/400 px, shared grid, wrapping, no panel overflow. `[hidden]` rule keeps `subs.hidden` effective. |
| 3. Card CSS matches the existing style | PASS | Styles in the existing output block of `nova.css`, `--nv-*` tokens, `.nv-card` appearance, selectors and data hooks preserved; browser test checks absence of static inline styles and consistent padding/frame. |
| 4. “läuftHauptagent: … Subagenten” row removed | PASS | `overview`, `statePill`, `agentLabel`, `countLabel` and their update sites removed; no active-code dangling references; guard switched to `[data-nv-out-cards]`; run state still visible in summary rows and main card. |

## Findings

All findings are minor and documentation-only. No code finding blocks acceptance.

1. [Minor] `docs/features/current/runs-output.md` described the removed status row by a positional phrase that did not precisely match its rendered placement. Suggested fix: describe the row without a positional claim.
2. [Minor] `docs/features/README.md` listed GH-88 under “Dashboard UI shell” although other output-view delivery records are indexed under “Agent runs and output”. Suggested fix: move the index entry.
3. [Minor/informational] `docs/features/GH-88.md` said log heights had been moved into CSS classes, while the dynamic `max-height` remains inline for focus/expand. Suggested fix: distinguish static CSS heights from the dynamic inline value.

The coordinator applied all three wording corrections after the review: the living-doc phrase was made position-neutral, the index entry moved to “Agent runs and output”, and the feature record now states that base log heights come from CSS while dynamic `max-height` stays inline. No behavior or scope changed; no re-review was required.

## Verification and limits

- Supplied evidence: tester red phase at `b525805` (`OutputCardBehaviorTest` 5 tests, `FAILED (failures=7)`; `SubGridTest` 2 tests, `FAILED (failures=1)`), green phase in the package worktree (5/5, 2/2, complete `test_output_ui` 54/54, classic preview tests 3/3), `node --check`, manifest check (70 files), syntax check (144 Python/8 Bash/5 JSON), `verify.sh quick` Exit 0.
- `verify.sh full` without flags: 2686 tests, 61/74 modules passed, 13 failed, Exit 7 solely from the missing baseline section for `VERIFY_ENV=head_of_vibe`. The pre-change comparison at `b525805` (same sandbox and env) showed 16 failed modules and the same label mismatch; no package-specific failure signature was introduced and no baseline or gate was changed.
- The reviewer had no shell access in this session, so no check was independently re-run. Findings rest on source reading and the supplied command outputs; the log files were cited by the coordinating agent.
- No weakening of existing assertions was found: the former overview count assertion was replaced by visible-card counting, and wait anchors were moved to stable elements with the same intent.

Verdict: PASS
