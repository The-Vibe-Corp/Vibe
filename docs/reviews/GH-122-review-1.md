# Independent Code Review — GH-122 (web UI after update)

## Short summary

The production fix is minimal and correct: `vibe_settings.py` is now part of
`PROGRAM_FILES`, matching all regular files shipped in `bin/`. The regression
tests are meaningful: they derive imports from both installed entry points,
guard the whole `bin/` program set, and start the installed dashboard up to
`/api/health`. Documentation, manifest entry, and the German Trillium note are
consistent with the supplied evidence.

One Medium blocker remains in a test-side fixture, described below.

Finding counts: **Critical — 0, High — 0, Medium — 1, Minor — 3**.

## Acceptance criteria status

| Criterion | Status | Evidence |
| --- | --- | --- |
| Fresh install/update copy every sibling module imported by `bin/vibe` and `bin/vibe-web.py` | PASS | `scripts/setup-vibe.py:43-68` covers all 24 `bin/` files. `test_program_files_cover_all_shipped_program_files` (`tests/unit/test_setup_vibe.py:347-363`) and `test_every_module_imported_by_the_installed_entry_points_is_installed` (`:379-391`) exercise it. Supplied: 67/67 OK. |
| Installed web UI starts and serves after update | PASS | `test_installed_web_entry_point_starts_without_missing_modules` (`:416-511`) installs the real repo via `mode="update"`, starts the installed `vibe-web.py` on a dedicated loopback port, and checks `/api/health` identity/port/token. Minor note below about `GET /`. |
| Regression test fails before the fix | PASS | The three new cases fail pre-fix by construction (missing set entry, AST-derived missing module, `ModuleNotFoundError`); supplied red-phase evidence matches. The retained `assertIn("vibe_autonomous", launcher)` keeps the V-021 guard meaningful. |
| Re-running update repairs an affected install without touching projects/personal data | PASS | `PROGRAM_FILES` drives install/update/rollback/uninstall (`setup-vibe.py:927-1031`, `1110`, `1336`, `1553`); missing files are copied (`test_reuse_keeps_existing_programs_and_only_adds_missing_ones`, `test_setup_vibe.py:540-551`); runtime data is preserved (`:521-538`); the dashboard test uses `mode="update"`. |

## Findings

### Required fix (Medium)

**Second test-side `PROGRAM_FILES` mirror not updated.**

- **Location**: `tests/unit/test_install_lifecycle.py:40-64` lacks
  `"vibe_settings.py"`.
- **Evidence**: `FreshInstallTest.test_fresh_install_copies_all_program_modules_and_writes_version`
  (`:219-235`) asserts set equality with `setup.PROGRAM_FILES` and a copy
  count; `ReuseTest.test_reuse_on_an_empty_target_records_the_version`
  (`:297-305`) asserts that `verify_installation` reports no failed checks.
  `setup.py:1336-1338` now requires the module, so the kit built from the
  stale mirror fails deterministically. The GH-122 doc's "no failure
  introduced" claim at module granularity does not account for this.
- **Correction (tester-owned)**: add `"vibe_settings.py"` to that mirror only,
  then rerun `tests.unit.test_install_lifecycle` and
  `tests.unit.test_setup_vibe` plus the package/full gate, and update the
  delivery record with the observed result.

### Optional suggestions (Minor)

- `docs/features/current/install-release.md:46` stated that the manifest
  covers 70 files while the current manifest covers 71; now updated.
- `docs/features/current/install-release.md:3` and
  `docs/trilium-index.md:3` carried older status dates; now updated.
- The installed-dashboard test verifies `/api/health` but not `GET /`. Adding
  a dashboard-HTML check would cover "serves the dashboard" more directly.
  Health is the documented readiness signal, so this is not blocking.

## Reviewed change set and verification limits

Reviewed the uncommitted working tree in `/home/vibe/VibeCode/vibe` (branch
`dev`, starting commit `8d8c89a`). Inspected `scripts/setup-vibe.py`,
`tests/unit/test_setup_vibe.py`, `tests/unit/test_install_lifecycle.py`,
`tests/unit/env_support.py`, `bin/vibe-web.py`, the manifest, feature docs,
and Trillium note `Nlwh8REdKhzP` (read-only; German, under "Features", matches
scope and repair instructions).

Verification limits: shell execution was denied during this review, so no
tests were run and no hashes were recomputed here. Supplied check outputs were
treated as claims; code and test paths were corroborated by source read-back.
The GH-122 document changed between the first and second read as verification
results were added; the current version was reviewed.

## Final verdict

Verdict: CHANGES REQUIRED
