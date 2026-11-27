# GH-124 — Independent review, round 1

Read-only review of the GH-124 package on `feature/m0p/gh-124` from start
commit `281272552f5740fb8029271082c6f89aebd79bbc`. The reviewer inspected the
ticket, the implementation, tests, documentation and the supplied check
evidence. The supplied evidence was reused; no acceptance check was rerun.

## Acceptance criteria

- **Expandable selection — PASS.** The model table lives inside
  `details[data-nv-models]` via the holder pattern. It is collapsed by default,
  hidden when collapsed, opens/closes correctly, and the refresh control stays
  visible in the section head. Supplied Playwright suite: 11/11 green.
- **Update, details and persistence — PASS.** `refresh_models` fetches all
  harness models, enriches them from the local catalogue through
  `vibe_models.enrich`, persists `info`/`info_unvollstaendig` in the cache and
  returns the enriched view immediately. Missing, incomplete and outdated
  values carry explicit reasons instead of unexplained "unknown"; success and
  failure feedback is explicit. Supplied unit suites green.
- **Catalogue section removal — PASS.** `details[data-nv-model-catalog]`, its
  `models-prices` action and the stale translation keys are gone; price editing
  remains available through the evaluations/costs area. The classic dashboard
  is byte-identical to the baseline.
- **Highlight and filter — PASS.** Configured models are marked with
  `data-nv-configured`/`nv-configured` and a CSS highlight. The configured-only
  filter is toggleable, persisted in `localStorage`, and correct after refresh,
  configuration changes and reload; covered by browser tests.

## Findings

- **Documentation consistency (minor, optional).** `docs/features/F34.md` and
  `docs/features/GH-57.md` retain historical model-section wording. Both files
  carry explicit GH-124 supersession notes added by this package, so the old
  text is a labelled historical record, not a contradiction or a blocker.
  Cleaning up the old bullets is optional.
- No Critical, High or Medium finding. No other proven blocker was found. The
  one genuine new failure observed during bootstrap (a modified protected
  `bin/web/app.js`) was corrected by reverting the file and separating the API
  payloads (`info` for the classic UI, `model_details` for Nova).
- The explicit baseline deviation is accepted: the new `head_of_vibe` section
  in `tests/verify-baseline.json` was promoted from an authorized
  `--write-baseline` bootstrap; the final `verify.sh full` reported
  `BASELINE-OK`, 2796 tests and Exit 0.

Verdict: PASS
