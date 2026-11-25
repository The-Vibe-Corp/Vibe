# GH-76 Review 1 — Hide the mandatory (template) AGENTS.md section

Independent review of work package GH-76, worktree `/var/log/custom/vibe-dev/worktrees/vibe-GH-76-BINdX3`, branch `feature/korbat/gh-76`, starting commit `fdc4def` (all package changes uncommitted in the working tree at review time).

## Summary

The package replaces the visible, per-run refreshed `vibe:general-rules` block in project `AGENTS.md` files with a hidden English platform text written once per run into the state directory and delivered to every opencode run via `OPENCODE_CONFIG_CONTENT.instructions`. The templates lose the managed block, `ensure_general_rules` and its call sites are removed, the AGENTS.md editor now fully supports block-less files while preserving legacy blocks byte-identically, and living docs plus the import manifest were updated. The implementation is fail-closed where the platform text cannot be delivered, the test evidence is test-first with documented HEAD comparisons for pre-existing failures, and the baseline change is exactly the one documented signature addition. I found no blockers; three minor, non-blocking suggestions.

Finding counts: Critical 0, High 0, Medium 0, Minor 3 (suggestions), Notes 4.

## Scope checked

All review was static (see limits). Files inspected in full or in relevant part:

- Production: `bin/vibe` (GENERAL_RULES removal, `PLATFORM_INSTRUCTIONS` alias at 101–108, `_agents_file_split`/`agents_file_view`/`agents_file_save`/`agents_file_create` at 2307–2414, `cmd_platform_instructions` at 2416–2442, dispatch at 6423, `cmd_run` GH-76 comment at 1690–1692), `bin/vibe_harness.py` (508–618: constant, path/writer, subcommand), `bin/vibe-run.sh` (943–1252: platform write, JSONC-safe config merge with `instructions`, `HAS_INLINE_CONFIG`, fail-closed aborts, server reuse), `bin/web/app.js` (604–632), `bin/web/i18n.js` (182–194, 1078, 1306).
- Templates: all five `templates/{generic,web,android,docker,rebuild}/AGENTS.md`.
- Tests: `tests/unit/test_gh76_platform_instructions.py` (all 446 lines), `tests/unit/runner_support.py` (`install_runner`), targeted inspection of `test_b1_project_agent_models.py` (300–379, 503–548), `test_ap2_opencode_agents.py` (1596–1622), `test_f31_agents_file.py` (test list incl. digest/marker/symlink cases), `test_ap8_github_checkout.py` (467–482), `test_f27_keep_changes.py` (709–712), `test_project_agents.py` (529, 544), `test_gh48_scaffold_templates.py` (176, 233), `test_vibe_paths.py` (779–786), `test_ap4_korbat_rules.py`.
- Docs/evidence: `docs/features/GH-76.md`, `docs/reviews/GH-76-test-agent-report.md` incl. both addenda, `docs/handbuch.md` (223–248), `docs/baseline.md` (254–255), `docs/import-manifest.json` (GH-76 entry, 1535–1551), `docs/verification_baselines.md`, `tests/verify-baseline.json` (complete).
- Hygiene: `.gitignore`, main repo `.git/info/exclude` (TICKET-GH-76.json and `.vibe/` excluded).

## Acceptance criteria

| # | Requirement | Status | Location / evidence |
|---|---|---|---|
| 1 | Hidden English platform instructions on every opencode project run | **PASS** | `bin/vibe-run.sh:943–953, 1181–1207` — always merges `"instructions": [abs path]` into `OPENCODE_CONFIG_CONTENT` (also without project models); tests: `test_gh76_platform_instructions.py` (9 cases), `test_b1` (`platform_instructions_path` helper asserts abs path, file exists, run+serve configs), `test_ap2:1596` (no-effective-entries case), `test_vibe_paths:779–786`. Green runs supplied (see limits). |
| 2 | Nothing in the user's global opencode config; nothing in project AGENTS.md | **PASS** | Delivery is inline-config only, file in `$STATE`; `test_gh76…:test_does_not_touch_a_project_agents_file_or_the_global_config` asserts byte-identical sentinels and path outside both. |
| 3 | Nothing auto-added to project AGENTS.md by init/new/clone/run/adoption | **PASS** | `ensure_general_rules` absent from `bin/` (grep: only marker constants + read-side helpers remain); `cmd_run` comment `bin/vibe:1690`; tests `test_project_agents:529,544`, `test_f27:709ff`, `test_ap8:467–482` (existing legacy block byte-identical, missing file created block-free). |
| 4 | Templates lose the managed block, keep type-specific content | **PASS** | All five templates read: no markers, no German rule headings; `test_gh76…` `TemplatesWithoutManagedRulesTest` (marker-free + per-type fragments), `test_gh48:176,233`. |
| 5 | User-template functionality/UI preserved (editor, create-from-template, backup/restore) | **PASS** | `agents_file_create` unchanged (`bin/vibe:2389–2414`); `agents_file_save` (`2347–2387`) preserves a legacy block byte-identically (before+managed+after reconstruction) or writes before+after, with digest, symlink, unpaired-marker and free-part-marker protections intact; `app.js:613–632` enables both textareas, keeps create button; backend `vibe-web.py` untouched. Tests: `test_f31` unit (15 cases) + browser (5/5 supplied), f33 save round-trip updated. |
| 6 | XML markers absent from the platform text | **PASS** | `PLATFORM_INSTRUCTIONS` (`vibe_harness.py:508–536`) contains no `<!--`; asserted in three tests (file, constant, discovery). |
| 7 | Higher priority than AGENTS.md | **PASS (supplied evidence)** | Orchestrator-verified against installed opencode v2.4.0 (GET /api/config shows the entry; configured instructions load after all AGENTS.md; inline config reaches all server sessions incl. subagents). The repo test `OpencodeInstructionDiscoveryTest` verifies real discovery via `opencode api get /api/config --standalone` (no model calls, skip-safe); ordering itself I could not re-verify (no execution). |
| 8 | A pre-running shared server without the entry is never reused | **PASS** | `vibe-run.sh:1243` (`HAS_INLINE_CONFIG != 1` gate) + `test_b1:503–527`. |
| 9 | Fail-closed when delivery fails | **PASS** | `vibe-run.sh:950–953` (write), `1196–1203` (merge), exit 2 with log reference. |
| 10 | Baseline change: exactly one documented added signature, nothing weakened | **PASS (see limit)** | `tests/verify-baseline.json:22–26` — old ap4 signature `e23e4f06…` retained, new `7ea99e31…` added for the rewritten module; `min_tests: 2500` matches `VERIFY_MIN_TESTS`; env matches `VERIFY_ENV=pi-aarch64-py3.14-namespaces`. HEAD comparison evidence documented in the test report §"Pre-existing failures". |
| 11 | Test authorship: only test agent changed tests; no weakening; `test_b16_git_rules.py` deletion justified | **PASS (as documented)** | Report §Provenance and §Deleted module. Static check: no weakened assertions found (digest/symlink/unpaired-marker cases all present); the deleted module's subject (German GENERAL_RULES text) no longer exists in production, and its equivalents (commit subject `<ID>:`, runner-owned Git, merge-conflict rules) are asserted as `PLATFORM_FRAGMENTS` in the new module. |
| 12 | Repo AGENTS.md underscore reference | **PASS** | `AGENTS.md:29` references `docs/verification_baselines.md`; doc exists; `AgentsMdReferenceTest` covers it. |
| 13 | Data hygiene / no secrets / runtime state excluded | **PASS** | `.gitignore` (`/.vibe/`, `/AGENTS.md`), repo exclude (`TICKET-GH-76.json`); no secrets in inspected change files; supplied `verify.sh quick` exit 0 (71 manifest files, syntax, no secrets). |

## Findings

### Required fixes (blockers/majors)

None.

### Minor (suggestions, non-blocking)

1. **Stale comment on the no-harness fallback** — `bin/vibe-run.sh:327–330` still promises "Ohne vibe_harness.py bleibt der bisherige direkte opencode-Pfad erhalten (ältere Installationen und Prüf-Attrappen)". Since GH-76, a missing `$BIN/vibe_harness.py` aborts the opencode run at lines 949–953 instead of using the direct path. The fail-closed abort is the correct behavior (a silent run without the platform text would violate the delivery guarantee, and the supported install/upgrade path always ships the module), but the comment now misdescribes that edge. Suggestion: update the comment (or note the behavior in `docs/features/GH-76.md`).
2. **Dead i18n keys** — `bin/web/i18n.js:184` and `:1306` ("Kein verwalteter Block vorhanden; dieser Teil bleibt leer.") and `:1078` ("Freier Text vor und nach dem verwalteten Block. Der verwaltete Block ist schreibgeschützt.") are no longer emitted by `bin/web/app.js` after the editor change. Harmless dead entries; optional cleanup.
3. **Cosmetic count mismatch in the new test module** — `tests/unit/test_gh76_platform_instructions.py:50` ("The four section headings") and the case docstring at 182–183 refer to four headings while `SECTION_HEADINGS` (51–57) holds five entries (title plus four sections). Wording only.

### Notes (no action required for GH-76)

- Pi runs intentionally receive no platform instructions (delivery is opencode-specific per the confirmed design); the Pi path is untouched.
- If a project's `.vibe/project.env` set `VIBE_STATE` into the project, the platform file would follow the configured state dir into it. This is a pre-existing, runner-owned configuration surface (the same variable also relocates harness.json/gates), not a GH-76 defect.
- The documented follow-ups outside GH-76 are honestly recorded: the latent Pi abort when a real `vibe_keys.py` is installed (test report addendum (c), delivery record) and the hyphen reference in the integration checkout's AGENTS.md (delivery record; agents must not touch that checkout — the worktree copy is corrected and gitignored).
- The `platform-instructions` seam via `$BIN/vibe_harness.py` instead of `$BIN/vibe` is sound: both entry points share `write_platform_instructions` (`vibe_harness.py:545`), the rationale (runner tests fake `bin/vibe`) is documented in `docs/features/GH-76.md` §Interface decision, `install_runner` copies the seam plus its `vibe_opencode` import, and both entry points are actually tested (subprocess via `bin/vibe` in the new module; module path in runner tests).

## Verification limits

- **No command execution was available to me** (shell tool permission-denied; Code Mode exposes no process/filesystem access). I therefore could not run `git status`/`git diff` against the starting commit `fdc4def`, could not execute any test or gate, and could not recompute manifest hashes or failure signatures. All run outputs cited above (red suite, focused runs, quick/package gates, browser 5/5, `verify.sh full` EXIT=0 BASELINE-OK with 2721 tests / 137 of 154 modules / 17 baseline-tolerated failed modules) are **supplied evidence** from the test report and the orchestrator, which I verified for internal consistency and against the inspected artifacts, not reproduced.
- The change-set composition is taken from the supplied brief and cross-checked by inspection (every declared file exists and matches its description); I could not independently enumerate the working tree relative to `fdc4def`.
- The ticket description beyond the first ~2000 characters was not readable with my tools (single-line JSON truncation in both read and grep previews); requirements were taken from the readable portion, the test report's derived contract, and the supplied brief. The tail appeared to contain the remainder of the suggested platform text, which the test's stable-fragment assertions cover.
- The ap4 pre-existing failure claim was spot-checked statically and is honest: `SPEC.md` contains no English Git heading at all, so `SpecCanonicalTest`'s canonical-heading cases (`tests/unit/test_ap4_korbat_rules.py:58ff`) fail for a reason predating GH-76 (earlier SPEC translation), exactly as documented.

## Reviewed revision

Worktree `/var/log/custom/vibe-dev/worktrees/vibe-GH-76-BINdX3`, branch `feature/korbat/gh-76`, HEAD `fdc4def`; the complete package change set is uncommitted in the working tree (production: `bin/vibe`, `bin/vibe_harness.py`, `bin/vibe-run.sh`, `bin/web/app.js`, `bin/web/i18n.js`, 5× `templates/*/AGENTS.md`; docs: `docs/features/GH-76.md`, `docs/handbuch.md`, `docs/baseline.md`, `docs/import-manifest.json`; tests: new `test_gh76_platform_instructions.py`, 21 modified modules, deleted `test_b16_git_rules.py`, `runner_support.py`, `tests/verify-baseline.json`).

Verdict: PASS
