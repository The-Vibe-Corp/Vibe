# GH-76 test agent report

Work package: GH-76 — "Hide the mandatory (template) AGENTS.md section"
Test agent: vibe-tester (independent session, test-first)
Date: 2026-11-25
Derivation basis: `TICKET-GH-76.json` (full description incl. the suggested platform text), `SPEC.md` (quality/acceptance), and the binding implementation contract confirmed with the user via `vibe ask` (question `q293832408128`, answered 2026-11-25T00:29:21Z, option A: inline config instructions). No implementation diff existed when the cases were derived; production code was unchanged while this report's red runs were executed.

Provenance: the case design and test authorship below are the test agent's. Where a run says "executed by orchestrator", the coordinator ran the test agent's tests verbatim on the test agent's behalf after the test agent's step budget ended; the commands are listed and repeatable.

## Contract under test (summary)

1. `bin/vibe` exposes `PLATFORM_INSTRUCTIONS` — the English platform text from the ticket without the `<!-- vibe:general-rules -->` marker comments — and a subcommand `vibe platform-instructions --directory DIR` that writes `DIR/platform_instructions.md` (atomic, refresh-safe, refuses symlinked destinations, prints the absolute path).
2. `bin/vibe-run.sh` merges `"instructions": ["<that path>"]` into `OPENCODE_CONFIG_CONTENT` for every opencode-harness run (not only runs with project models), preserving existing config keys; runs must not silently reuse a pre-running shared server that lacks the entry.
3. The built-in German `GENERAL_RULES` block is no longer written into project `AGENTS.md`: `ensure_general_rules` and its call sites (`vibe init`, `vibe new`, adoption, `vibe run`) are removed; all five `templates/*/AGENTS.md` lose the marker block while keeping their type-specific content.
4. The AGENTS.md editor stays fully usable: a legacy managed block is preserved byte-identically on save; block-less files (the new normal) save `before` + `after`; unpaired-marker, marker-in-free-parts, digest and symlink protections are unchanged; `agents_file_create` unchanged.
5. Repository `AGENTS.md` references `docs/verification_baselines.md` (underscore), not the broken hyphen variant.
6. Nothing is written into any project `AGENTS.md` or the user's global opencode configuration by the platform-instructions path.

## Cases (name / precondition / action / expected)

The full per-case docstrings live in the test files; each case is described in place (German is the suite's existing convention for test docstrings).

### New module `tests/unit/test_gh76_platform_instructions.py`

- `PlatformInstructionsCommandTest.test_writes_the_ticket_platform_text_and_prints_its_absolute_path` — empty state dir; run subcommand; exit 0, last stdout line is the absolute file path, file contains the four section headings and stable fragments (`Verdict: PASS`, `Verdict: CHANGES REQUIRED`, `docs/reviews/<ID>-review-<round>.md`, `TICKET-<ID>.json` with `state`/`commit`/`test`, `<ID>:` commit subject, runner-owned Git and merge-conflict rules); no `<!--`, no `vibe:general-rules`, no German rule headings.
- `test_refreshes_an_existing_file_idempotently` — tampered file between two runs; both exit 0, same path, content restored byte-identically, exactly one file.
- `test_platform_constant_matches_the_written_file_without_markers` — `PLATFORM_INSTRUCTIONS` equals the written file; no marker pair in the constant.
- `test_refuses_to_follow_a_symlinked_destination` (symlink-capable environments) — symlinked destination; non-zero exit, target untouched, message mentions `Symlink`.
- `test_does_not_touch_a_project_agents_file_or_the_global_config` — sentinels in a project `AGENTS.md` and `$HOME/.config/opencode/opencode.json` stay byte-identical; the written file lies outside both.
- `TemplatesWithoutManagedRulesTest.test_all_templates_drop_the_german_general_rules` — all five `templates/*/AGENTS.md` contain no marker pair and no German rule headings.
- `TemplatesWithoutManagedRulesTest.test_templates_keep_their_type_specific_content` — each template keeps `# Projekt: {{NAME}}` and its type-specific fragments (generic/web/android/docker/rebuild).
- `AgentsMdReferenceTest.test_agents_md_references_the_underscore_baseline_document` — `AGENTS.md` names `docs/verification_baselines.md`, not the hyphen variant; the file exists.
- `OpencodeInstructionDiscoveryTest.test_written_file_is_discovered_as_an_instructions_entry` — real `opencode api get /api/config --standalone` (throwaway HOME/XDG, no model calls, skips when the opencode binary is unavailable or a standalone server cannot start); the absolute path appears in an `instructions` list of the returned config documents.

### Updated modules (contract changes; obsolete old-contract assertions removed)

- `test_f31_agents_file.py` — non-canonical legacy block saved byte-identically; block-less file saves both parts (old "kein verwalteter Block" error gone); create-from-template produces a block-free file; protections unchanged.
- `test_project_management.py` — init leaves existing AGENTS.md byte-identical; new projects get block-free AGENTS.md from templates; shipped templates carry no managed block.
- `test_project_agents.py` — `cmd_run` neither injects nor updates a block.
- `test_gh48_scaffold_templates.py` — scaffold copies templates without adding a block; no template-block byte-identity checks remain.
- `test_f27_keep_changes.py` — `vibe run` leaves AGENTS.md untouched whether clean or dirty; no `ensure_general_rules` patch targets remain.
- `test_ap5_korbat_init_adopt.py`, `test_ap8_github_checkout.py` — adoption creates a missing AGENTS.md from the block-free template; an existing legacy block is preserved byte-identically; failure injection moved to `copy_tree`.
- `test_ap4_korbat_rules.py`, `test_ap7_korbat_rules.py` — removed the German-block/template byte-identity cases; kept SPEC/GitHub-docstring and baseline-manifest checks; ap7 asserts the corrected `AGENTS.md` baseline reference.
- `test_ap06_github.py` — `CommitMessageRuleTest` (German completion-rule fragments) removed.
- `test_ap03_agent_management.py`, `test_b3_password_auto_setup.py`, `test_v025_agent_start_repair.py`, `test_f22_preflight_assist.py`, `test_v026_run_isolation.py`, `test_run_autostop.py` — obsolete `ensure_general_rules`/`GENERAL_RULES` patch targets removed; behavior assertions unchanged.
- `test_ap2_opencode_agents.py` — the no-effective-entry case now expects `instructions` injection and `--standalone`.
- `test_b1_project_agent_models.py` — `platform_instructions_path()` helper; asserts `OPENCODE_CONFIG_CONTENT.instructions == [absolute path]` for agent invocations and the private server, preservation of project-model keys alongside `instructions`, and that a pre-running shared server without the entry is not reused.
- `runner_support.py` — `install_runner` copies the explicit runner module list plus `vibe_harness.py`/`vibe_opencode.py` (the runner's platform-instructions seam); see the addendum for the corrected fixture scope.

### Deleted module

- `tests/unit/test_b16_git_rules.py` — its whole subject was the German git/completion rules text inside `GENERAL_RULES`, which GH-76 removes and replaces with the English platform text (covered by the new module). Deletion is intentional, not a weakening: the equivalent runner-facing rules are asserted in `test_gh76_platform_instructions.py`.

### Browser cases

- `tests/browser/test_f31_agents_file_ui.py` — legacy block fixture is now a literal non-canonical block; new `test_blockless_file_allows_editing_both_parts_and_saves_them` (both textareas enabled for a block-less file, save persists `before + after`; intended red against `bin/web/app.js` which currently disables the upper textarea when `managed === null`); explanation-wording expectations updated.
- `tests/browser/test_f33_project_ui.py` — the settings-tab save round-trip now expects a non-canonical legacy block to be preserved byte-identically instead of being normalized.

## Red evidence (before any implementation; production code unchanged)

Executed by the test agent unless noted "executed by orchestrator".

| Command | Result |
| --- | --- |
| `bash scripts/verify.sh quick` | exit 0 (unchanged production passes the quick gate) |
| `python3 -m unittest tests.unit.test_gh76_platform_instructions -v` | 9 tests, FAILED (9 failures, 2 errors): missing subcommand/constant, templates still carry the block, broken baseline reference (executed by orchestrator, matching the test agent's earlier run) |
| `python3 -m unittest tests.unit.test_f31_agents_file` | 15 tests, FAILED (3 failures, 1 error) |
| `python3 -m unittest tests.unit.test_project_management` | 23 tests, FAILED (7 failures, 1 error) |
| `python3 -m unittest tests.unit.test_project_agents` | FAILED (2 failures): `cmd_run` still injects/updates |
| `python3 -m unittest tests.unit.test_gh48_scaffold_templates` | FAILED (6 failures) |
| `python3 -m unittest tests.unit.test_ap7_korbat_rules` | FAILED (1 failure): intended baseline-reference red |
| `python3 -m unittest tests.unit.test_f27_keep_changes` | FAILED (1 failure): intended clean-file red |
| `python3 -m unittest tests.unit.test_b1_project_agent_models` | FAILED (5 failures): no instructions path in the runner wiring |
| `python3 -m unittest tests.unit.test_ap2_opencode_agents` | FAILED (1 failure): intended |
| `python3 -m unittest tests.unit.test_ap8_github_checkout -v` | 33 tests, FAILED (3): 2 intended reds (block-free template creation, byte-identical legacy preservation) + 1 pre-existing (see below) (executed by orchestrator) |
| `python3 -m unittest tests.unit.test_ap4_korbat_rules` | FAILED (4 failures): all pre-existing SPEC-heading mismatches (see below) |
| `python3 -m unittest tests.unit.test_ap06_github tests.unit.test_ap5_korbat_init_adopt tests.unit.test_run_autostop tests.unit.test_v025_agent_start_repair tests.unit.test_f22_preflight_assist tests.unit.test_v026_run_isolation tests.unit.test_b3_password_auto_setup tests.unit.test_ap03_agent_management` | combined batch OK / expected-green; only obsolete patch targets were removed (executed by orchestrator; consistent with the test agent's per-module results) |
| `python3 -m unittest tests.browser.test_f31_agents_file_ui -v` | 5 tests, FAILED (3 failures): block-less editing blocked by `app.js`, card wording, save normalization — all intended reds (executed by orchestrator) |
| `python3 -m unittest tests.browser.test_f33_project_ui -v` | 29 tests, FAILED (2 failures, 4 errors): 1 intended red (save round-trip normalization) + 5 pre-existing (see below) (executed by orchestrator) |

## Pre-existing failures separated from GH-76 reds

Demonstrated with the original (HEAD) test modules run in the same environment against unchanged production code — the comparison evidence required by `docs/verification_baselines.md`:

- `test_ap8_github_checkout.test_the_shipped_test_agent_is_replaced_by_the_local_template` — fails identically at HEAD (1 failure in the original module run). This is the module's baseline-accepted failure.
- `test_ap4_korbat_rules` (original at HEAD) — 4 SPEC-heading failures (`SpecCanonicalTest`), caused by the earlier SPEC translation; the rewritten module keeps these checks, so the same 4 pre-existing failures remain until the SPEC question is resolved outside GH-76.
- `test_project_management` (original at HEAD) — 5 failures + 1 error around shipped-template TESTER configuration and the shipped test-agent template; these existed before GH-76 ("template-fixture gaps").
- `tests.browser.test_f33_project_ui` (original at HEAD) — 4 `PriorityTest` Playwright errors and `WorkOrderTest.test_work_tab_follows_the_contract_order` fail identically at HEAD (unrelated to the AGENTS.md feature).

The committed baseline (`tests/verify-baseline.json`, env `pi-aarch64-py3.14-namespaces`) currently tolerates one signature each for `test_ap4_korbat_rules`, `test_project_management`, `test_ap7_korbat_rules`, `test_ap8_github_checkout`; the HEAD comparison above shows additional pre-existing signatures. Per `docs/verification_baselines.md`, any residual pre-existing signature that the final full run reports as unaccepted (exit 7) must be recorded in `tests/verify-baseline.json` with this comparison evidence, and the package review must identify that change explicitly.

## Contract notes (not resolved by guessing)

- "A pre-running shared server without the instructions entry must not be reused" goes beyond the ticket's literal text; it is required so the delivery guarantee ("available on each project run") holds when a server predates the run. Implemented and tested as part of the contract.
- The platform file's directory is passed by the caller (`--directory`), so state-vs-runtime placement stays an implementation detail of the runner wiring.
- The symlink case expects the error message to mention `Symlink` (fail-closed with a clear reason, matching suite conventions).

## Commands for the coder (re-run after implementation)

    python3 -m unittest tests.unit.test_gh76_platform_instructions tests.unit.test_f31_agents_file tests.unit.test_project_management tests.unit.test_project_agents tests.unit.test_gh48_scaffold_templates tests.unit.test_f27_keep_changes tests.unit.test_ap4_korbat_rules tests.unit.test_ap7_korbat_rules tests.unit.test_ap06_github tests.unit.test_ap5_korbat_init_adopt tests.unit.test_ap8_github_checkout tests.unit.test_ap2_opencode_agents tests.unit.test_b1_project_agent_models -v
    python3 -m unittest tests.browser.test_f31_agents_file_ui tests.browser.test_f33_project_ui -v
    bash scripts/verify.sh quick
    bash scripts/verify.sh package

Every case above was actually executed; a non-executed test is not evidence. Test files were written and changed only by the test agent; no production code was modified for this report.

## Addendum (2026-11-25): runner fixture correction

### (a) Fixture correction and reason

The first version of `tests/unit/runner_support.py::install_runner` copied every
`bin/vibe*` file into the temporary installation. That unintentionally installed
`vibe_keys.py`. `bin/vibe-run.sh` key-syncs every harness when that module is
present and aborts the agent start when the sync fails; for the Pi harness the
sync is unsupported ("Harness 'pi' wird für den Key-Sync nicht unterstützt (nur
opencode)"). This produced a false red in
`tests/unit/test_ap14_runner_continue.py::RunnerPiNeverContinuesTest::test_pi_branch_never_receives_a_session`.

Root cause: the new runner seam does not call `bin/vibe`. It calls
`bin/vibe_harness.py platform-instructions` (so runner tests that replace the
CLI entry with a fake still exercise the real platform path). `bin/vibe` only
delegates to the same shared implementation for the CLI seam used by the unit
tests.

Correction: `install_runner` now copies the explicit HEAD list
(`vibe-run.sh`, `vibe_runs.py`, `vibe_packages.py`, `vibe_questions.py`,
`vibe_autonomous.py`, `vibe_storage.py`, `vibe_github.py`, conditionally
`vibe_tickets.py`) plus `vibe_harness.py` and its import `vibe_opencode.py`.
`vibe_keys.py` stays out of the fixture exactly as at HEAD, preserving the
documented "older installation without key sync" branch.

### (b) Re-run results (green)

Executed in the package worktree with the implemented production code:

| Command | Result |
| --- | --- |
| `python3 -m unittest tests.unit.test_ap14_runner_continue tests.unit.test_b1_project_agent_models tests.unit.test_ap2_opencode_agents tests.unit.test_f27_keep_changes -v` | `Ran 100 tests in 125.709s` — **OK** |
| `python3 -m unittest tests.unit.test_gh76_platform_instructions -v` | `Ran 9 tests in 4.923s` — **OK** |

No case in these modules still fails. The dedicated GH-76 delivery cases
(`instructions` path, preserved model keys, private-server delivery, shared
server not reused) and the unchanged `vibe run`/AGENTS.md behavior are green.

### (c) Latent pre-existing production observation (follow-up, outside GH-76)

When a real `vibe_keys.py` is present in the installed `$BIN` (the normal
installation), `bin/vibe-run.sh` starts a key-sync for **every** harness. For
the Pi harness that sync fails and the run aborts before the Pi agent starts.
The older installation without `vibe_keys.py` skips the sync and works. This
behavior predates GH-76 and was only hidden by the old test fixture, which did
not copy `vibe_keys.py`. It is recorded here as a follow-up observation; GH-76
does not change production for it, and the fixture intentionally restores the
HEAD scope so the latent defect is not conflated with this package.

Correction (2026-11-25): `test_f31_agents_file_ui.test_card_shows_content_managed_block_and_explanation` targeted the removed canonical text "Ordnung im Git halten"; it now targets the non-canonical fixture block ("Bestandsregel F31") that production correctly displays byte-identically. Re-run: `python3 -m unittest tests.browser.test_f31_agents_file_ui -v` → 5 tests, OK; `python3 -m unittest tests.browser.test_f33_project_ui -v` → 29 tests, only the five documented pre-existing failures (4 PriorityTest errors + work-tab order).

Correction (2026-11-25, second addendum): `tests/unit/runner_support.py::install_runner` again copies the optional `vibe_limits*.py` and `vibe_gates*.py` globs from HEAD (V-027/AP10 compatibility), while keeping the explicit module list with `vibe_harness.py`/`vibe_opencode.py` and still excluding `vibe_keys.py`. The stale `test_vibe_paths.RunnerPathsTest` curl-health assertion (pre-GH-76 shared-server probe) was replaced by the new contract evidence: the platform text exists in the configured state directory. Re-run: `python3 -m unittest tests.unit.test_ap10_gates tests.unit.test_v027_limits tests.unit.test_vibe_paths -v` → 82 tests, OK. `test_f31_agents_file_ui` EXPLANATION now matches `bleibt byte-identisch erhalten|preserved byte-identically` (old per-run-update wording removed, docstring fixed); `python3 -m unittest tests.browser.test_f31_agents_file_ui -v` → 5 tests, OK.

Review suggestion (2026-11-25, GH-76-review-1): wording-only correction in `test_gh76_platform_instructions.py` — the comment now says "the title heading plus the four section headings" and the case docstring says "the five headings in SECTION_HEADINGS"; no assertion or tuple changed. Re-run: `python3 -m unittest tests.unit.test_gh76_platform_instructions -v` → 9 tests, OK.
