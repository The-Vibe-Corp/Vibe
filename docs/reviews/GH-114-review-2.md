# Focused Re-Review — GH-114 (post-Medium-fix)

**Work package:** GH-114 — cost overview ui improvements
**Worktree:** <package-worktree> (branch `feature/m0p/gh-114`)
**Start commit:** `9d72dc6c33a595b5e26c99dcdc435302e558ca19`
**Reviewer stance:** read-only; no files changed, no tests run, no report written to disk.

## What changed since review 1 (verified against current file state)

- `bin/web/nova-evals.js`: added `nvEvalGroupedPrice(text, separator)` (validates grouping: first group 1–3 digits, subsequent groups exactly 3) and rewired `nvEvalParsePrice()` to locale-aware disambiguation via `nvEvalLocale()` (de-DE: `.` = grouping / `,`=decimal; en-US: `,`=grouping / `.`=decimal; both separators present → last is decimal; single grouping-valid separator → strip; otherwise decimal).
- `docs/import-manifest.json`: refreshed `bin/web/nova-evals.js` entry to bytes `41634`, sha256 `23da90c9…` (confirmed current).
- Tests/docs: two new `CostsOverviewUiTest` cases + shared helper (`assert_price_inputs_saved_as`); tester report and delivery record updated with RED/GREEN proof.

## Medium defect — resolution check

- **Resolved:** Yes. The defect (lone separator treated as decimal regardless of locale → `1.234`/`1,234` parsed as `1.234`) is corrected by the grouping-aware logic. Red output (`1234 != 1.234 within 6 places`) → green after fix; isolated green run and full class run `Ran 8 tests in 22.077s — OK` (exit 0) both pass, including the de (`1.234 €`→1234, `1.5`→1.5) and en (`1,234 €`→1234) cases.

## Regression / locale-rule check

- Hand-traced post-fix parser against accepted formats: de `1,50 €`→1.5; de `1.5`→1.5; de `1.234,50`→1234.5; en `1,5`→1.5; en `1.5`→1.5; en `1,500.50`→1500.5; invalid inputs still rejected. No-drift attributes/logic untouched. Locale grouping rule behaves as specified.

## Remaining findings blocking handoff

- None blocking. The only outstanding items are the Minor, non-blocking a11y suggestion (expand toggle lacks `aria-controls`); the prior docs-link minor is resolved (`docs/reviews/GH-114-review-1.md` now exists).

## Verdict

The required Medium fix is fully resolved without regression, the locale rule is sound, and no remaining blocker blocks handoff.

Verdict: PASS
