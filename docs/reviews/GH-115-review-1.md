# Independent Code Review — GH-115 "prio view on small screen is missing content"

**Work package:** GH-115 — prio view on small screen is missing content
**Type:** feedback / prioritization view
**Worktree:** /home/vibe/vibe-logs/worktrees/vibe-GH-115-cQ70bq (branch `feature/m0p/gh-115`)
**Start commit:** `64054cd1db833f2afdb3493ef66d2e049c005373`
**Reviewer stance:** read-only source review (no files modified by this session; the shell tool was permission-denied in this reviewer session, so no live Git diff or test execution was possible from here; the delivered evidence was taken from the supplied check outputs and verified against the code by read-back).

## Short summary

The delivered change set for GH-115 implements the ticket's core ask: the small-device (mobile) prioritization view no longer shows only the obsolete single `open` status, but all implementation-relevant, non-closed statuses, ordered by a single status precedence with priority only as an intra-status tie-break.

Backend (`bin/vibe_packages.py`):
- `STATUS_PRECEDENCE = ("in-progress", "open", "blocked", "waiting-merge")` with `STATUS_RANK` and `DRAFT_RANK` (lines 402-404).
- `status_rank(record)`, `processing_key(record, index)` = `(status rank, priority P0..P8, store index)` or `None` for draft/done/unknown (lines 407-421).
- `standard_key(record, index)` = display order variant that keeps drafts (at `DRAFT_RANK`) visible but excludes done/unknown (lines 424-436).
- `priority()` maps unset/`P`-less to 9 (last) (lines 386-390).
- `select_package` fallback sorts runnable candidates (`open`/`in-progress`) by status before priority; `_ready()` gate unchanged (lines 568-649).
- `priority_view()["standard"]` reuses `standard_key` and excludes `done`, keeps `draft` at the end (lines 1332-1411).

Frontend (`bin/web/nova-project.js`):
- `nvpRawState` normalizes `ready`/`Ready` → `open` plus legacy display states (lines 105-116).
- `NVP_IMPLEMENTATION_STATES = ['in-progress', 'open', 'blocked', 'waiting-merge']` with `nvpImplementationState` (lines 118-127).
- `nvpWorkView` renders the priority strip only on mobile (`min-width: 769px`) and passes the item list (lines 509-534).
- `nvpPriorityStrip` builds the eligible set from implementation states, orders configured → standard → remaining rows, drag/save via `/api/priority` (lines 1161-1382).

Acceptance criteria status, locations and evidence:

1. **Small-screen prioritization view shows all applicable non-closed tickets (draft excluded by documented decision, Closed excluded).** — **PASS (supported)**
   - Locations: `bin/vibe_packages.py:1332-1411` (`standard`), `bin/web/nova-project.js:1178-1382` (`nvpPriorityStrip`), `bin/web/nova-project.js:509-534`.
   - Evidence: independent tester red phase on pristine start commit (`['AP2','AP1'] != ['AP1']`, `['AP4','AP3','AP5','AP2','AP1'] != ['AP2','AP1']`), final green run of the same cases; GH-56 `test_19_mobile_priority_view_shows_all_non_closed_except_draft` (`tests/browser/test_work_ui.py:3375-3404`) expects `["AP2","AP1","AP4","AP5"]` (In Progress, Ready, Blocked, Waiting-Merge; no Draft, no Done).

2. **In Progress always before Ready regardless of priority; priority only within status group; status over priority.** — **PASS (supported)**
   - Locations: `bin/vibe_packages.py:402-436`, `bin/vibe_packages.py:568-633`, `bin/vibe_packages.py:1394-1403`; frontend order sources `bin/web/nova-project.js:141-163` and `:1178-1199`.
   - Evidence: browser cases `test_08` (4023-4058), `test_08a_mobile_priority_status_precedes_priority` (4060-4078), `test_08b_mobile_priority_orders_only_within_status_group` (4080-4103), `test_08c_mobile_priority_orders_other_states_before_priority` (4105-4129) all green; unit selection tests `tests/unit/test_priority.py:178-206`, `tests/unit/test_worknotes_sync.py:582-650`, `tests/unit/test_github_issues.py:2371-2391`.

3. **Draft never implemented; kept visible in backend standard (GH-47 contract) but excluded from mobile strip.** — **PASS (supported)**
   - Locations: `bin/vibe_packages.py:424-436` (draft via `DRAFT_RANK`), `bin/vibe_packages.py:601-608` (`_ready`), `bin/web/nova-project.js:118-127`, `:1178-1200`.
   - Evidence: GH-47 draft tests remain green (`tests/unit/test_priority.py:253-278`, `tests/unit/test_github_issues.py:2393-2404`); browser `test_08` and count tests (`tests/browser/test_work_ui.py:4037-4151`) green.

4. **Saved `PACKAGE_ORDER` remains authoritative (AP11); status precedence governs automatic/standard order.** — **PASS (supported)**
   - Locations: `bin/vibe_packages.py:452-566` (`package_order`), `bin/vibe_packages.py:568-633` (order-first selection), frontend `:1178-1199` (configured before standard).
   - Evidence: `tests/unit/test_priority.py:208-217` (package order beats priority), `tests/unit/test_priority.py:999-1038` (order/queue unchanged with configuration); browser `test_12_prio_count_after_reorder_updates_without_reload` (4188-4214).

5. **Existing functionality, data and tests remain functional; no test weakening.** — **PASS (supported), with pre-existing baseline failures documented separately.**
   - Evidence: tester-updated expectations were strengthening moves, not weakenings: F29 standard order `["T2","T1","T3","T4","T5","F1"]` → `["T2","T1","T3","T5","F1","T4"]` (blocked after open, `tests/unit/test_priority.py:961-966`); worknotes sync store-order now expects in-progress first; GitHub-issues eligibility now expects in-progress before ready. GH-47 draft test byte-identical and green.

## Findings

### Required fixes
**None.**

### Optional suggestions (minor, non-blocking)
1. **Living-doc completeness (Minor/Suggestion):** `docs/features/current/work-packages.md` (Records, ~line 81-95) and `docs/features/current/ui-shell.md` (Records, ~line 104-113) list prior ticket records but do not add a GH-115 entry, although the "Selection order" sections were updated. Suggested fix: add the GH-115 record link.
2. **Trillium wording (Minor/Suggestion):** note `89kJlya6mQai` was read via the Trillium MCP tools (`get_note_content`, `search_notes`). Content is German and factually accurate against the delivered code; one phrase ("Der Zähler … zählt alle sichtbaren Einträge, nicht mehr nur Ready") is slightly loose — it counts eligible *configured* entries. Wording-only, no behavior impact.
3. **Naming smell (Minor/Suggestion):** `nvpPriorityStrip(name, token, view, items, cards)` — the fifth parameter is the work surface container used for badge refresh, misleadingly named `cards`.
4. **Cosmetic (Minor/Suggestion):** strip row labels render `P<n> ` only when the entry came from a saved configuration; standard-order entries get no priority prefix (ordering still conveys priority).

## Verification evidence summary

- Red/green: 5 new/changed browser cases failed on the pristine start commit (also via `git archive` control) and the final run was green (`Ran 5 tests — OK`).
- Focused units: `test_worknotes_sync` 56 OK; `test_priority` + `test_work_packages` 173 tests with 3 failures, all pre-existing `NovaWaitingSurfaceTest`, reproduced at start commit; `test_github_issues` 93 tests with 5 failures, all pre-existing `NovaIssuesSurfaceTest`, reproduced at start commit. Control run of those three modules at start commit: 289 tests / same 8 failures.
- Static/package: `bash scripts/verify.sh quick` exit 0; `bash scripts/verify.sh package` exit 0; `node --check bin/web/nova-project.js` OK.
- Full: unflagged `bash scripts/verify.sh full` → exit 7 solely due to `VERIFY_ENV=head_of_vibe` lacking a committed baseline section; with `--env pi-aarch64-py3.14-namespaces`: 2762 tests, 15 failed modules; four "new" signatures byte-identical to start-commit documentation (`docs/features/GH-109.md:74-75`) and reproduced via control archive. No baseline/gate/threshold changed.
- Browser: `tests.browser.test_work_ui` final 98 tests, 10 failures, all `Ap11PriorityBrowserTest`; start-commit control: 95 tests, same 10 failures (stale `TICKETS.md` fixture) → no new browser regression from this package.

## Verification limits

- This reviewer session could not execute Git commands or tests (shell permission denied); review is based on supplied evidence plus file reads.
- Full-run caveat documented above; pre-existing baseline failures were not counted as findings of this package.

## Trillium assessment

- German note `89kJlya6mQai` ("GH-115 — Priorisierungsansicht auf kleinen Bildschirmen", parent: Features) read via Trillium MCP; content matches delivered scope, status order, draft handling and verification claims. Language: German as required. Minor wording imprecision only.

## Summary

- Critical: 0 — High: 0 — Medium: 0 required fixes — Low/Minor: 2 optional suggestions recorded above.
- No required fixes; no Critical/High/Medium finding attributable to GH-115 remains.
- No new regression, no API/CLI contract break, no dead code, no weakened assertions found in the delivered change set.

Verdict: PASS
