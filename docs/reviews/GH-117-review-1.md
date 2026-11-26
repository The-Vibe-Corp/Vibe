# Independent Code Review — GH-117 (setting storage)

## Short summary

Work package GH-117 adds local, version-tolerant persistence of the five personal user settings (theme light/dark/auto, accent color, enabled/disabled features, favorite projects, favorite agents) via a new versioned store at `<state>/settings.json`, an authenticated `/api/settings` GET/POST pair, HTML-meta bootstrap, frontend boot/migration/write-through in the Nova shell, browser and unit tests, and documentation/manifest updates.

The implementation was read back in full during this review and the design, per-key fallback, merge semantics, atomic write path, auth ordering, HTML escaping, migration logic and test coverage are substantively sound. The supplied verification evidence (red/green runs, existing suites, quick/package exits, manifest and syntax checks, full run with environmental baseline mismatch) is broadly coherent and, where re-checked by source read-back, matches the code.

Finding counts by severity: **High — 1 (requires a fix before PASS)**, **Minor — 1 (optional suggestion)**, **Critical — 0**.

## Acceptance criteria status

1. **Persist the five settings in the local application directory** — **PASS**. Implementation: new `bin/vibe_settings.py` (`FILENAME = "settings.json"`, `SCHEMA_VERSION = 1`, `path(state_dir)` at `bin/vibe_settings.py:71-73`; defaults at `:57-63`; effective per-key resolution at `:186-198`; store API `load/view/update` at `:201-317`). Write path uses atomic `vibe_storage.write_text` (line 310). Covered by unit tests (`test_update_roundtrip_writes_versioned_file_and_loads_all_five_settings`, `tests/unit/test_settings_storage.py:133-164`) and browser tests.

2. **Version tolerance, safe per-setting fallback, never lose other saved settings** — **PASS** for implementation and tests. `_file_version` (`bin/vibe_settings.py:98-109`) handles missing/invalid/lower versions; `_effective` (`:186-198`) falls back per key; unknown keys and higher versions are preserved on write (tests `test_newer_version_keys_are_ignored_in_view_but_preserved_on_write` at `:246-275`). One defect noted below (write-path race).

3. **Survive updates/reopen; keep existing functionality and tests working** — **PASS** with environmental caveats. Restart/persistence behavior verified by `test_settings_survive_a_server_restart_with_same_state_dir` (`tests/unit/test_settings_storage.py:570-591`) and browser restart test; existing suites reported green; full-run failures were traced to a missing `head_of_vibe` baseline section and to pre-existing failures, with the 15 final failures a subset of the 17 control-run failures.

4. **Add tests for save/load/migration/fallback** — **PASS**. 24 unit cases and 5 browser cases; red/green evidence supplied (22 real backend failures on pristine start commit before implementation, then 24 OK; browser 5/5 failing before, then green twice).

5. **Docs, import manifest, Trillium** — **PASS** per supplied checks (`check-import-manifest.py` OK with 71 files; `check-syntax.py` OK; `node --check` OK).

## Findings

### Required fix (High)

**Lost-update / silent data-loss risk on concurrent settings writes.**

- **Location**: `bin/vibe_settings.py` — read in `update()` at lines ~249-251 (`data, exists = _read_document(state_dir)`), write at line 310 via `vibe_storage.write_text(path(state_dir), text)`.
- **Evidence**: `_read_document` (lines 76-95) reads the file without snapshot/digest capture or lock participation, and `vibe_storage.write_text` (defined at `bin/vibe_storage.py:358-360`, backed by `write_bytes` at `:343-355`) accepts an `expected` conflict parameter that the settings module does not pass. The storage layer therefore provides optimistic-concurrency conflict detection (`check_expected`, `ConcurrentChangeError`) that is bypassed here; the write is unconditional last-write-wins over a possibly-stale read.
- **Consequence**: With the threaded HTTP server and per-tab-only frontend save serialization (`NV.saveSettings`, `bin/web/nova-core.js:452-474`, chains saves but only within a tab), simultaneous saves (e.g., two browser tabs toggling features/favorites) can merge against stale state and overwrite each other, silently dropping a just-saved user change — contrary to the ticket requirement of never losing saved settings.
- **Recommended correction**: capture the file snapshot/digest before merging, pass it as `expected` to `vibe_storage.write_text`, and handle `ConcurrentChangeError` by re-reading and re-merging (retry), preserving partial-patch semantics.

### Optional suggestion (Minor)

- Settings writes use plain `vibe_storage.write_text` rather than the backup-aware `write_text_with_backup`; atomic replace already prevents partial content, but the project's configuration rules favor backup-before-change. Not a ticket requirement; consider adopting the backup flow for settings if backup semantics are desired.

## Supplied evidence vs. read-back observations

- **Supplied (not re-run during this read-only review)**: red/green backend and browser results; existing suite results; `quick`/`package` exits; manifest/syntax/node checks; final full run (2786 tests, 64/79 modules, 15 failed, Exit 7 due to missing `head_of_vibe` baseline section) with control run at start commit (2762 tests, 61/78, 17 failed, same Exit 7); all 15 final failures subset of the 17 control failures; corrections of two package-caused failures and re-verification.
- **Read-back (performed during this review)**: confirmed auth ordering and guards for `/api/settings` (GET at `bin/vibe-web.py:1360-1366` behind `_authorized`; POST at `1652-1660` behind the same guard plus `_guard(True)`/allowlist), strict JSON-object enforcement returning 400 for non-object bodies (`_read_json`, `bin/vibe-web.py:1272-1305`), HTML-escaping via `html.escape(..., quote=True)` (`_settings_meta`, `bin/vibe-web.py:2809-2820`), meta replacement only in `page()` with classic shell untouched, frontend boot/migration/save-through logic in `bin/web/nova-core.js:312-666` and `boot()` at `:1441-1462`, pin helper delegation in `bin/web/nova-home.js:71-106` and `bin/web/nova-agents.js:111-160`.

## Reviewed change set and verification limits

- Change set: new `bin/vibe_settings.py`; modified `bin/vibe-web.py`, `bin/web/index.html`, `bin/web/nova-core.js`, `bin/web/nova-home.js`, `bin/web/nova-agents.js`, tests, docs; new tests `tests/unit/test_settings_storage.py`, `tests/browser/test_settings_storage_ui.py`; fixture resets added in three existing browser test modules.
- Limits: this was a read-only source review; no additional commands or tests were executed per final instructions; supplied check outputs were treated as claims and key implementation details were corroborated by source read-back.

## Final verdict

Verdict: CHANGES REQUIRED
