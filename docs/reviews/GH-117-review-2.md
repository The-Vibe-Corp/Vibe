# Focused Re-Review — GH-117 (round 2: blocker resolution + post-review fixes)

## Scope of this re-review

- Verification of the round-1 blocking fix in `bin/vibe_settings.py::update()`.
- Verification of the two janitor fixes in `bin/web/nova-core.js`.
- Check of the newly added tests and that no existing test contract was weakened.

## 1. Round-1 blocking finding — lost update on concurrent settings writes — RESOLVED

Read-back of the corrected `bin/vibe_settings.py::update()` confirms the fix is coherent:

- It reads via `vibe_storage.read_snapshot(target)` and applies the pure merge helper `_merge_patch(data, patch)` (no I/O inside → retry-safe).
- It preserves the no-op path (returns before writing when `changed` is false; `stored` reflects the snapshot).
- It passes `expected = snapshot if snapshot.exists else vibe_storage.MISSING` into `vibe_storage.write_text(...)`, so the storage layer's optimistic conflict detection is actually engaged.
- On `vibe_storage.ConcurrentChangeError` it retries (bounded by `MAX_WRITE_ATTEMPTS = 8`), re-reading and re-merging on the fresh state, instead of overwriting blindly.

Verified properties: no data loss; unknown keys and higher schema versions preserved (merge starts from copies of the raw settings/top-level data); ignored-key semantics unchanged; no-op behaviour unchanged.

Error-path check: the post-fix exhaustion raise is covered — the broad handler in `bin/vibe-web.py:2748-2749` maps any escaping exception (including `ConcurrentChangeError`) to a structured 500, so no new unhandled-error defect was introduced by the correction.

Test evidence corroborates the fix: `tests/unit/test_settings_storage.py::test_concurrent_partial_updates_do_not_lose_each_other` (lines 391-424) models a competing write during the outer write; the red run (`'dark' != 'light'`) and green run match the pre-fix blind overwrite versus post-fix retry behaviour.

## 2. Janitor fix 1 — `NV.saveSettings` keepalive byte-length guard

`bin/web/nova-core.js:456-483` now uses `TextEncoder().encode(JSON.stringify(payload)).length < 60000` with a fallback that disables keepalive. Verified correct; consistent with the large-CJK browser test preconditions (`test_large_cjk_favorites_are_persisted`).

## 3. Janitor fix 2 — frontend favorite normalization limits

`normalizeNames` / `normalizeAgents` in `bin/web/nova-core.js:354-383` now enforce string type, non-empty values, length limit, list cap (200) and deduplication, matching the backend. Verified consistent; the new `test_invalid_favorite_entries_are_not_mirrored_optimistically` asserts client and server use the same limits.

## 4. New-defect check on the additional fixes

No new blocking defect was introduced: the hypothesized unhandled-exception path for the retry exhaustion is already handled by the broad POST handler, the keepalive fix is correct, and the normalization fix is consistent. A minor, non-blocking theoretical note exists (frontend counts UTF-16 units vs. backend code points for astral-plane characters in the new length check); it does not block.

## 5. Verification status (as supplied; read-back corroborated the code)

Backend 25/25 OK; related unit suites `test_storage` + `test_web_routes` + `test_i18n` 99/99 OK; browser 7/7 OK with both new cases red in throwaway copies before their fixes; quick/package, manifest, syntax and node checks green; final full run 2787 tests, 64/79 modules, 15 failed, Exit 7 solely due to the missing `head_of_vibe` baseline section; control run at the start commit showed 17 failures, with all 15 final failures a subset.

## Focused verdict

The single blocking finding from round 1 is resolved in code and behaviour, and the two post-review fixes introduced no new blocking defect.

Verdict: PASS
