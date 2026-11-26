# Independent Code Review — Work Package GH-108 (Nova project detail UI)

**Worktree:** /home/vibe/vibe-logs/worktrees/vibe-GH-108-hnRVem (branch `feature/m0p/gh-108`) — reviewed against start commit `b3e02092d1ee70399f1aa081ffbddec7b7c5cf90`; complete change set: `bin/web/nova-project.js`, `bin/web/nova.css`, `bin/web/i18n.js`, `docs/import-manifest.json`, `docs/features/GH-108.md`, `docs/features/current/ui-shell.md`, `docs/features/current/work-packages.md`, tests in `tests/unit/test_work_packages.py`, `tests/browser/test_work_ui.py`, `tests/browser/test_project_ui.py`, `tests/browser/test_tickets_ui.py`.

## Summary

The GH-108 change set implements all eight ticket items in the Nova project detail. The implementation inspected via targeted reads is broadly coherent: run-state-driven disabling of `Start Working`, dropdown for Check/Full Verification, hero placement of ticket-creation actions, quick-filter row + content-sized search, full-width sidebar fields, Markdown description rendering with a distinct detail wrapper, session/run-gated Continue, in-progress return paths, and Show Done placement. Documentation and i18n additions are present.

Finding counts by severity:
- Critical: 0
- High: 0
- Medium: **1** (required fix identified)
- Minor: 2 (suggestions only)

## Acceptance criteria

1. **`Start Working` clickable only when no run is active; disabled otherwise** — **PASS**. `nv-hero` run button (`data-nv-run-start`) with initial disabled state, `/api/run-state` poll (`nvpStartRunPoll`, 4 s interval, `NV.stale` guard, `if (runButton.disabled) return`), post-load sync from `view.run.running` / `data.running`. Evidence: `bin/web/nova-project.js:2266–2277, 2429–2431, 245–272`; unit test `NovaProjectDetailControlsTest.test_start_working_button_is_disabled_while_a_run_is_active`.

2. **Check and Full Verification in dropdown, reachable, not primary** — **PASS**. `details[data-nv-more-actions]` / `summary.nv-more-summary` (`Weitere Aktionen`); quick via `nvpButton(..., 'verify', ...)` (class `nv-btn`, not primary), full via raw button `data-nv-verify="full"`. CSS for collapsed menu in `nova.css:1760–1779`. Evidence: unit test `test_check_and_full_verification_are_in_an_actions_dropdown`; browser `ChecksTest.test_checks_buttons_and_quick_verify_started`.

3. **Add Package / Report Bug / Give Feedback in `nv-hero`, all tabs** — **PASS**. Hero actions row (`data-nv-action` new-package/new-bug/new-feedback) rendered via `replaceChildren(hero, ...)`, outside panels. Evidence: unit test `test_new_ticket_actions_live_in_the_header_on_every_tab`; browser `WorkTest.test_work_order_and_no_board`.

4. **Quick filters above search; search not full width** — **PASS**. `chipRow` (kind/state chips) before `searchRow` (`NV.filterBar(chipRow, searchRow)`); CSS `.nv-work-chips, .nv-work-search-row { flex: 1 1 100% }`, `.nv-work-search-row .nv-search { flex: 0 1 20rem; width: auto; max-width: 24rem }`. Evidence: unit test `test_quick_filters_precede_search_and_search_is_not_full_width`; browser `test_28_quick_filters_above_search_desktop`, `test_29_filter_bar_no_overlap_or_overflow_mobile`.

5. **Sidebar fields full width; view-mode description formatted (Markdown/line breaks/code blocks)** — **PASS with note**. CSS `[data-nv-ticket-form] label.nv-field … { width: 100%; max-width: 100% }` overrides general `max-width: 32rem`. Description via `nvpMarkdownBlock` → `nvMarkdown` (DOM-only, fenced code blocks, headings, lists, quotes), wrapper class `nv-ticket-detail-desc` with `data-nv-ticket-description` (not the clipping `.nv-ticket-desc`). Note: paragraph lines are joined with a single space, so literal single-newline breaks within one paragraph collapse; fenced code blocks and block structure are preserved.

6. **Continue clickable only when no project session running** — **PASS**. `nvpSessionsBusy` checks payload `running`, flat sessions (`starting`/`running`) and per-package sessions; `nvpSetResumeBusy` disables in-progress resume buttons; poll refreshes; handler guards. Evidence: unit test `test_continue_button_is_disabled_while_a_session_is_running`; browser state/ownership cases.

7. **In Progress can move back to Draft/Ready via card/DnD/details; blocked/waiting-merge/done runner-owned** — **PASS** with **one Medium defect** (see Findings).

8. **Show Done directly right of search** — **PASS**. `hideDoneButton` as second child of `searchRow` after `NV.search(...)`; `previousElementSibling` has `data-nv-search`. Evidence: unit test `test_show_done_button_is_directly_after_the_search_input`; browser `BoardTest` and `GH56WorkBrowserTest.test_26_hide_done_next_to_search_and_effective`.

## Findings

### Required fix (Medium)

**Contradictory UI state for in-progress tickets in the detail panel.**
- Location: `bin/web/nova-project.js`, `nvpOpenTicketDetail`, approximately lines 904–939 (state-select branch and the `if (rawState === 'in-progress')` runner-notice block).
- Evidence: GH-82 delivery record states the detail offers the state select only for `draft`/`open` and shows the read-only notice (`data-nv-runner-state-notice`, "Zustand wird vom Läufer gesetzt") for `in-progress`, `blocked`, `waiting-merge`. GH-108 supersedes this for the source state `in-progress` and adds the draft/open select (comment at `nova-project.js:912–913`), but the runner-notice block for `in-progress` was left in place.
- Consequence: an in-progress ticket now shows both a functional draft/open state select **and** a notice claiming the status is runner-owned — a direct contradiction of the implemented GH-108 behavior and of ticket item 7. No test asserts the in-progress notice; tests assert its presence only for `blocked`/`waiting-merge` and its absence from the pre-select slice for in-progress.
- Required fix: remove the `in-progress` runner-notice branch (keep notices for `blocked`/`waiting-merge`; keep the done evidence notice), then re-run focused checks (`NovaProjectDetailControlsTest`, `WorkStateOwnershipTest`, ticket-detail browser cases).

### Optional suggestions (Minor)

1. Redundant session-busy computation: `nvpSessionsBusy(view.sessions)` is computed twice (lines 2432 and 2637) and passed as `baseBusy`; code-quality pass already flagged as non-blocking.
2. Markdown paragraph handling joins lines with a space; if literal line breaks within a paragraph are required by product wording, adjust the renderer.

## Test quality (as far as verifiable without re-running)

- Red phase evidence: 8 new structural tests vs. pristine HEAD → `FAILED (failures=10)`; intended failure messages indicate genuine pinning of new behavior (missing dropdown, header actions, session lock, blocked DnD targets, misplaced Show Done, narrow sidebar).
- Post-fix green: `NovaProjectDetailControlsTest` 8 OK; `tests.unit.test_i18n` 29 OK; updated browser cases OK; clipping regression fixed with distinct wrapper class + red/green regression assertion. No assertions were observed weakened; red-phase failure on pristine HEAD implies additive expectations.
- Protected states: backend `WEB_TICKET_STATES` limited to `draft`/`open` (`TicketApiTest.test_state_action_allows_only_draft_and_open`); blocked/waiting-merge keep notice without select; done keeps evidence protection. Browser coverage present for blocked/waiting-merge and done.

## Documentation consistency

`docs/features/GH-108.md`, `docs/features/current/ui-shell.md`, `docs/features/current/work-packages.md` are consistent with the implemented behavior and the GH-82 supersession for in-progress.

## Verification limits

Supplied (not independently re-run by this reviewer): `verify.sh quick` Exit 0; `verify.sh package` Exit 0; focused green runs; `verify.sh full` unflagged Exit 7 (2761 tests, 64/78 modules, 14 failed; env-label mismatch `head_of_vibe`; start-commit isolated comparison also Exit 7 with same common failures, no GH-108-specific regression). Shell access was unavailable, so hashes and tests could not be recomputed here.

## Verdict

A genuine Medium defect remains in the delivered change set (contradictory in-progress runner notice alongside the new state select). Required fix identified; affected focused checks should be re-run after correction.

Verdict: CHANGES REQUIRED
