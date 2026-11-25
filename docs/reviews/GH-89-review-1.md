# GH-89 Review — Runde 1

Paket: GH-89 „Fix various test bugs" · Worktree `/var/log/custom/vibe-dev/worktrees/vibe-GH-89-xZpTIR` (Branch `feature/korbat/gh-89`) · Start-Commit `31667f5` · Änderungsstand: uncommitteter Arbeitsbaum (Commit durch den Koordinator nach dem Verdict).

## Summary

I inspected the complete change set against the supplied start commit. Because shell access was denied to this reviewer (no `git diff`, no test reruns), I established the audit basis differently: the integration checkout at `/opt/custom/vibe-dev/workspaces/vibe` sits at exactly the start commit (`refs/heads/dev` = `31667f55…`), so every changed file could be compared manually old-vs-new, and the supplied verification logs (`/dev/shm/gh89-full-1.log`, `/dev/shm/gh89-cmp/start-commit-modules.log`) were read in full and match the claimed evidence.

The implementation correctly addresses F1-1..F1-3 (per-instance `/dev/shm` roots, source≠target bind for `/tmp/opencode`, no remaining host write path), F1-4, F1-5, F1-6 and F1-7. Tests genuinely pin the new behavior and no existing assertion was weakened. Docs and manifest are consistent. F1-8 is correctly excluded per ticket. No Critical, High or Medium findings; two minor suggestions.

Finding counts: Critical 0, High 0, Medium 0, Minor 2.

## Acceptance criteria

| Criterion | Status | Location | Evidence |
|---|---|---|---|
| F1-1/F1-2/F1-3: shared `/tmp/opencode` no longer created or written; per-instance roots | PASS | `bin/vibe_sandbox.py:92-96` (constants), `:335-349` (`_map_opencode_write_dir`), `:352-399` (`status()`, mapping applied to both branches), `:689-712`, `:753-760` (extra_write_dirs mapping, `--bind backing /tmp/opencode`), `:776-777` (`--remount-ro /tmp` after binds) | Read of the full module: all `write_dirs` entries pass through the mapping (project, default, caches, state, extras), `check()`/`_ensure_dir` therefore only touch `/dev/shm` roots; `--tmpfs /tmp` precedes the source≠target bind, `--remount-ro /tmp` follows it, so the backing stays writable inside the private tmpfs. Pins: `tests/unit/test_sandbox.py:36-38, 296-308` (asserts `("--bind", backing, "/tmp/opencode")` and no shared bind), `test_costs_refresh.py:375-384` (fallback `/dev/shm/vsb-<uid>`), `test_private_server.py:296`. Residual `/tmp/opencode` strings in `test_sandbox.py` are only `VIBE_SANDBOX_ROOT` values for fallback path computations (no fs writes). |
| F1-4: working hint for missing `VIBE` | PASS | `install-vibe.sh:5` | `test_setup_vibe.py:1150-1164` asserts the exact hint `VIBE=<workspace> bash install-vibe.sh` and that nothing is installed. |
| F1-5: `--yes` suppresses install/log/deps prompts | PASS | `scripts/setup-vibe.py:1468, 1481, 1722` (`interactive and not options.yes`) | `YesFlagPromptTest` (`test_setup_vibe.py:827-922`): calls `main()` with `interactive=True` and a recording `input_fn`, asserts zero prompts across three scenarios; genuinely red against the old code. Wrapper prompt path (always `--vibe`/`--update`) has no remaining prompt. |
| F1-6: hermetic wrapper test; runner stdin | PASS | `test_setup_vibe.py:1094-1148` (stdin=DEVNULL, XDG/VIBE_CONFIG stripping, child output surfaced on timeout); `scripts/run-tests-parallel.py:117, 121-131`; `test_run_tests_parallel.py:93-101, 173-190` (pty-backed case) | Old WrapperTest (`/opt/custom/vibe-dev/workspaces/vibe/tests/unit/test_setup_vibe.py:843-871`) had neither `stdin=` nor XDG stripping; the new version strictly strengthens it, no assertion dropped. |
| F1-7: foreign install target leaves `profiles.prod` untouched; new `--set-default` | PASS | `scripts/setup-vibe.py:459-485` (`_same_install_target` via `Path.resolve(strict=False)` — handles symlinks and `..`; `_default_profile_install` → `None` for missing file/profile/invalid config, so those write as before), `:1671-1679`, `:1699-1706` (dry-run), `:1795-1815` (skip + guidance), `:1389-1393` (flag) | `DefaultProfileProtectionTest` (`test_setup_vibe.py:925-1074`): byte-identical config including no backup file, `--set-default` repoints, same target and missing `install` key still write, dry-run reflects the decision. B17 interplay intact: the running-install guard is untouched; when target == configured install, config is written as before. |
| F1-8 | Correctly excluded | — | Ticket excludes it; package doc states this. |
| Full verification | PASS (as supplied evidence) | `/dev/shm/gh89-full-1.log` | Log read directly: "Gesamt: 2731 Tests, 65/76 Module bestanden, 11 fehlgeschlagen", BASELINE-OK list matches exactly the 11 failed modules, Exit 0. `/dev/shm/gh89-cmp/start-commit-modules.log` shows the start-commit failure sets for `test_install_lifecycle`, `test_sandbox`, `test_private_server` in a full-run-like environment. All GH-89-touched modules are green in the full run. |

## Findings

Required fixes: none.

Optional suggestions:
- **Minor (suggestion, doc wording):** `docs/features/F6.md:94` now says "`--yes` ohne Rückfragen" and `:144` says "`--yes` ohne Modus: `reuse`", but the workspace prompt (`setup-vibe.py:1457`) and the reuse/update question (`:1637`) still fire on a TTY even with `--yes` (deliberately untouched by design). The five prompt sites the doc names are accurate; the two blanket sentences overstate it slightly. A one-word qualification ("bei `--vibe` bzw. mit `--reuse`/`--update`") would make the doc match the code.
- **Minor (suggestion, edge case):** In `bwrap_argv`, a directory that realpaths to the opencode backing itself (`/dev/shm/vibe-opencode-<uid>`, e.g. if a user lists it explicitly in `permissions.json`) is bound as source≠target to `/tmp/opencode` instead of at its own path. Write access is still granted (at the aliased path), so no operational defect; worth a comment only.

## Reviewed revision and verification limits

- Reviewed: working tree of `/var/log/custom/vibe-dev/worktrees/vibe-GH-89-xZpTIR` (branch `feature/korbat/gh-89`) against start commit `31667f5` (comparison base: integration checkout at that exact commit). All listed change-set files read; no unexamined deviations found in the files I compared.
- Limits: shell execution was denied, so I could not run `git diff` myself, rerun tests, or recompute manifest hashes; manifest checksums and the `check-import-manifest` result rest on the supplied evidence (green in the full run, `test_import_manifest` 8/8 OK). First-exception signature equality between the full run and the start-commit comparison log was taken from the supplied evidence; I verified the module failure sets visually. Repo hygiene: no private paths or secrets introduced; remaining `/tmp/opencode` mentions live only in historical record sections that are explicitly marked as pre-GH-89.

Verdict: PASS
