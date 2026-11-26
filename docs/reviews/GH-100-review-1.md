# Review — GH-100 "Umsetzung GH-88 fehlerhaft" (round 1)

Independent read-only review of work package GH-100 in worktree `feature/m0p/gh-100`, start commit `abc9f94`. No files were modified by the reviewer. The report is based on the supplied change set and check output; the reviewer had no shell access in this session.

## Summary

Work package GH-100 corrects the Nova agent-output layout from GH-88 in `bin/web/nova.css`, `bin/web/nova-output.js`, `tests/browser/test_output_ui.py`, and supporting docs. The full change set was reviewed against the start commit `abc9f94` and the five acceptance criteria.

Finding counts by severity: **0 Critical, 0 High, 0 Medium, 3 Minor** (no required fixes identified).

## Acceptance criteria — status and evidence

1. **Compact overview as responsive grid** — PASS. `.nv-out-summary` is a grid (`repeat(auto-fit, minmax(min(100%, 22rem), 1fr))`, `align-items: start`, `max-width/min-width: 0`) and `.nv-out-summary-row` is a wrapping flex row, moved from removed inline styles into `nova.css` (lines ~1224–1245) and rendered by `nova-output.js` (`div.nv-out-summary`, `[data-nv-out-summary-row]`, `data-nv-summary-target`, `data-focus`). Red phase failed as intended; green phase OK (SummaryOverflowTest incl. 1400/900/600/400 px viewports).

2. **Main vs. subagents: main full-width row above sub grid** — PASS. `.nv-out-main-wrap { grid-column: 1 / -1; }` (nova.css line 1266) with main card preceding `[data-nv-out-subs]` (`display: contents`) in the shared `.nv-out-cards` grid (nova.css lines 1250–1257, nova-output.js lines 271–273). Exactly one main card exists per run by design; sub articles are the grid items below. Verified green at 1200 px (SubGridTest).

3. **Both grids: available width, no horizontal scrollbar, column reduction, single column + wrap below minimum** — PASS. `minmax(min(100%, …), 1fr)` tracks with `min-width: 0` on containers/items; `.nv-log` keeps `pre-wrap` + `overflow-wrap: anywhere`; heads use `flex-wrap: wrap`. Green at 1400/900/400 px (sub grid) and 1400/900/600/400 px (summary); no horizontal overflow asserted and passing.

4. **Definite heights adapted at breakpoints; no growth with output; vertical scroll** — PASS. `.nv-out-main { height: 22rem; overflow: auto }`, `.nv-out-sub-log { height: 16rem; overflow: auto }`; breakpoints ≤900 px → 18/13 rem, ≤600 px → 16/12 rem; `.nv-out-log-open` → `height: auto`; enlarged overlay `.nv-out-enlarged .nv-log { flex: 1 1 auto; height: auto; max-height: none; overflow: auto }`. Fixed-height tests prove height stability within 2 px while `scrollHeight` grows and `overflowY` is auto; long-output test scrolls internally. Green.

5. **Behavior/layout/scope otherwise unchanged** — PASS. Follow mode (hold-position + follow-to-bottom, main and sub), focus/expand/Escape, steering, hooks, aria, classic `.bv-*` view: covered by existing green tests (`OutputCardBehaviorTest`, F33 `FocusTest`, `ControlsPlacementTest`, `SubagentSteerTest`, `SummaryTest`, classic-view classes in the same module). `setLogLimit()` now toggles the `nv-out-log-open` class; aria-expanded/text/follow-refresh logic preserved.

## Findings

- Minor (optional suggestion): dead test helper. `tests/browser/test_output_ui.py:4127` defines `F34OutputBrowserTest.parse_limit()`, which asserted the now-removed inline `max-height` contract. No call sites remain. Suggested fix: delete the helper.
- Minor (optional suggestion): stale test docstrings. `MainCardTest.test_main_card_structure` (~line 4342) and `SubGridTest.test_card_structure_and_padding` (~line 4561) still quote the old inline `max-height <= 60vh` / `<= 40vh` contract even though the assertions now use `assert_fixed_window` against the fixed CSS height. Suggested fix: update docstrings.
- Minor (optional suggestion): breakpoint documentation. `docs/features/GH-100.md` ("Breakpoints are 900 px and 600 px, matching the existing Nova layout scale") does not match the pre-existing Nova shell breakpoints (1023/639 px etc.); 900/600 are new values introduced by this package. Documentation wording only.

No Critical, High, or Medium findings; no unmet criteria, no weakened assertions found without replacement, no horizontal-overflow or focus/follow regression detected.

## Verification and limits

- Change set reviewed against `abc9f94`: `bin/web/nova.css`, `bin/web/nova-output.js`, `tests/browser/test_output_ui.py`, new `docs/features/GH-100.md`, `docs/features/current/runs-output.md`, `docs/features/README.md`, `docs/features/GH-88.md` pointer, `docs/import-manifest.json`.
- Supplied check results accepted as evidence: red phase (`FAILED failures=12`, intended), green phases (`Ran 14 … OK`; `test_output_ui` 58 OK; `test_subagent_ui` 10 OK; combined 61 OK), `node --check` OK, import-manifest OK (70 files), syntax check OK, `verify.sh quick`/`package` Exit 0, `verify.sh full` Exit 7 (documented `VERIFY_ENV=head_of_vibe` baseline mismatch, corroborated by pristine comparison at `abc9f94`).
- Verification limits: shell access was unavailable in this session, so no check was independently re-run; conclusions rest on the supplied change set, file contents read directly, and the supplied check output.

Verdict: PASS
