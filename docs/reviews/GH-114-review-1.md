# Independent Code Review — GH-114 "cost overview ui improvements"

**Work package:** GH-114 — cost overview ui improvements
**Worktree:** <package-worktree> (branch `feature/m0p/gh-114`)
**Start commit:** `9d72dc6c33a595b5e26c99dcdc435302e558ca19`
**Reviewer stance:** read-only; no files changed, no tests run, no report written to disk.

I first read the root `AGENTS.md` (Developing Vibe) and the additionally supplied `docs/AGENTS.md` (agent/roles rules); the latter is relevant context for the role-badge logic in AC3.

## Short summary

The delivered change set (as supplied) covers `bin/web/nova-evals.js`, `bin/web/nova.css`, `docs/import-manifest.json`, `tests/browser/test_activity_ui.py`, `docs/reviews/GH-114-test-report.md`, `docs/features/GH-114.md`, `docs/features/current/costs-diagnostics.md`, and `docs/trilium-index.md`, plus the external Trillium note `V5ZLRDvPvRcq`.

Overall assessment: the implementation broadly satisfies the four acceptance criteria, and the supplied red/green verification evidence is coherent. The USD no-drift fix (`data-nv-price-display` / `data-nv-price-eur`) was re-derived by hand and is correct. The locale-aware formatting, dedup/roles logic were checked against the backend contract in `bin/vibe` (`_project_stats`, `_price_for`, `costs_set_prices`). However, one genuine defect was found in the newly delivered tolerant price parser, which blocks a clean PASS.

## Finding counts by severity

- Critical: 0
- High: 0
- Medium: 1 (required fix)
- Minor: 2 (optional suggestions)

## Acceptance criteria — status, location, evidence

1. **Compact single-line project list** — **PASS (supported)**
   - Location: `bin/web/nova-evals.js:356-396` (project rows), `374-378` (project cell/name); `bin/web/nova.css:1565-1591`.
   - Evidence: New browser test `test_project_rows_stay_single_line_with_long_name_at_1400_and_900px` passed in the final run; the red run confirmed the missing `[data-nv-cost-name]` hook; CSS implements `white-space: nowrap`, ellipsis truncation with `title` tooltip, `table-layout: fixed; min-width: 46rem`, nowrap on cost-table cells, and horizontal scroll in `.nv-table-wrap`; row/cell height ≤ 44 px verified at 1400 px and 900 px.

2. **Structured, locale-formatted monthly summary** — **PASS (supported)**
   - Location: `bin/web/nova-evals.js:133-139` (`nvEvalMonthField`), `245-264` (`drawSummary`), `302-314` (month card); `bin/web/nova.css:1594-1615`.
   - Evidence: Green browser tests for de-DE and en-US; structured card with month pill and five labelled fields; no overflow at 900 px.

3. **All models incl. subagents, dedup, roles** — **PASS (supported)**
   - Location: `bin/web/nova-evals.js:398-475` (price map / model collection / roles); backend aggregation `bin/vibe:4565-4653`.
   - Evidence: Green editor test (exactly three models, dedup via `seen`, agent badges from usage + `/api/project-agents`); backend merges per-model across agent keys consistently.

4. **Currency fields after settings/locale, validation, correct save/display** — **PASS for flow, FAIL for edge input handling (see Medium finding)**
   - Location: `bin/web/nova-evals.js:46-131` (`nvEvalMoney`, `nvEvalPriceInput`, `nvEvalParsePrice`), `568-617` (`savePrices`); tests at `tests/browser/test_activity_ui.py:2082` and `:2201`.
   - Evidence: USD no-drift fix verified by hand (display→stored round-trip) and proven red→green via the drift regression test (`0.1234 != 0.12336134453781514 within 6 places` before fix, green after). Locale formats (`1,50 €`, `0,25 €`, `2,00 €`, `1.5`) accepted; invalid values (`-1`, `abc`, ``) rejected without POST — green.

## Findings

### Required fix (Medium)

1. **Tolerant price parser mishandles thousands-only notation — silent wrong price storage.**
   - Location: `bin/web/nova-evals.js:107-131` (`nvEvalParsePrice`), especially the normalization block at lines 113-126.
   - Defect: When an input contains exactly one separator and no second separator, the implementation treats that single separator as the decimal separator. German thousands notation without a fractional part (e.g. `1.234` or `1,234`) is therefore parsed as `1.234` instead of `1234`; English grouping notation (e.g. `1,234`) is likewise misread as a decimal.
   - Consequence: A user entering a whole-number price with grouping separators gets a silently wrong EUR base price persisted through `POST /api/costs`, which then feeds incorrect cost aggregation (`bin/vibe:4543-4548`).
   - Evidence: Parser verified against all test-covered formats (`1.5`, `1,50 €`, `0,25 €`, `2,00 €`, `$1,500.50`-style multi-separator cases); the thousands-only case is untested and misparsed.
   - Recommended correction: disambiguate using locale-aware grouping rules (de-DE: dot = grouping unless a comma decimal follows; en-US: comma = grouping unless a dot decimal follows), instead of blanket "single separator = decimal".

### Optional suggestions (Minor, non-blocking)

2. The expand toggle button (`bin/web/nova-evals.js:367-373`) uses `aria-expanded` but no `aria-controls`; the detail row it toggles is not programmatically associated.

3. `docs/features/GH-114.md` references `../reviews/GH-114-review-1.md`, which is not present in the worktree at review time (pending the coordinator saving this review).

## Verification evidence summary

- Red run on clean start commit: `Ran 5 tests — FAILED (failures=13, errors=4)`; final implementation: `Ran 6 tests — OK` (finals 14.4 s, exit 0).
- Focused class check: `CostsTest` final state identical to clean control copy at `9d72dc6` → classified `BASELINE-OK` (pre-existing F34 fixture debt).
- Static checks: `node --check bin/web/nova-evals.js` OK; `bash scripts/verify.sh quick` and `bash scripts/verify.sh package` exit 0; `tests.unit.test_ui_style_reference` OK (classic UI byte-identical).
- Full run: exit 7 without flags due to `VERIFY_ENV=head_of_vibe` lacking a baseline section; with `--env pi-aarch64-py3.14-namespaces` the failure set (15 modules) is a subset of the start-commit control run (17 modules), and the four signatures flagged as new match the documented start-commit signatures → baseline classification accepted as correct.

## Verification limits

- This reviewer session could not execute Git commands (`git status` / `git diff 9d72dc6` permission denied), so the change set could not be re-diffed here; review is based on the supplied change list and file reads.
- No independent re-run of the full suite was possible in this session; evidence is taken from the supplied tester/coordinator outputs.

## Verdict

Changes required: the delivered tolerant price parser contains a genuine Medium defect (thousands-only notation misparsed → silent wrong price storage) that must be fixed, re-tested, and re-reviewed.

Verdict: CHANGES REQUIRED
