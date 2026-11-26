# Final independent review report — GH-104

**Work package:** GH-104 „project - output UI: orphaned subagents"
**Worktree:** isolated package worktree on `feature/m0p/gh-104` (Vibe logs area)
**Change set:** vs. start commit `ffa0058` (branch `feature/m0p/gh-104`)

Report saved by the coordinating agent from the independent reviewer's final handoff.
Shell execution was denied in the reviewer session; quoted check output was supplied by
the tester/coordinator and is distinguished from the reviewer's own inspection.

## Short summary and findings by severity

The final evidence update was reviewed against the completed full run.

Final full run (`bash scripts/verify.sh full --env pi-aarch64-py3.14-namespaces`): **exit 7** — `Gesamt: 2753 Tests, 63/78 Module bestanden, 15 fehlgeschlagen`.

- 12 modules reported `Bekannt rot` — accepted by the committed baseline for `pi-aarch64-py3.14-namespaces`.
- 3 modules reported `Neue Regression` — `tests.unit.test_license` (`sha256:e0bb80d15c59ad32bdf96d7dff03366721245021c4ff1195496b1584004d5db4`), `tests.unit.test_release` (`sha256:ad272edbedd04ee6d276c522e65ba60513045640b3fda258c044525e85153b58`), `tests.unit.test_repository_hygiene` (`sha256:a2bdaecbff50dc4025491ee25cddbfe3b246bd9ba66eef2e800ab6554ef77c6f`).
- Pre-existence proof: identical `verify_engine.failure_signature` values (module + error class + normalized message → sha256, `scripts/verify_engine.py:506-522`) at start commit `ffa0058` in an independent local clone — equal to the package run. The failures are content checks of untouched files (README licence placeholder; historical personal-home-path mentions in pre-existing docs/reviews), not GH-104 behaviour.
- Committed baseline is stale for these signatures; canonical baseline updates are not permitted inside a package; no baseline/config change and no gate weakening was made; the documented pre-existence procedure was followed.
- One environment-dependent failure was identified (`test_local_test_agent_preserved_when_environment_established`, missing ignored local `.opencode/agents/test-agent.md`) and is not a package regression; it was not the first exception used for the module signature.

**Findings by severity:** Critical 0, High 0, Medium 0 outstanding, Minor 2 (no required fixes outstanding).

## Acceptance criteria — status and evidence

1. **Trace lifecycle from execution to UI state; fix underlying cause** — **PASS**. State model `bin/vibe_runs.py:197-264` (`subagents` = active list, `history` = bounded 50-entry list), retirement `bin/vibe_runs.py:277-306`, per-attempt reset `bin/vibe_runs.py:332-349`, revival `bin/vibe_runs.py:310-328`; API projection `bin/vibe-web.py:233-545`. Focused green: `python3 -m unittest tests.unit.test_gh104_subagent_cleanup tests.unit.test_output_view_runner tests.unit.test_output_view_api` → `Ran 112 tests ... OK`.
2. **Remove from active UI at first terminal state (success/fail/cancel), not waiting for parent** — **PASS**. Terminal statuses (`completed`, `error`, `failed`, `cancelled`, `canceled`) retire immediately via terminal events incl. opencode `tool_use` task events and Pi `tool_execution_end`; concurrent children stay active.
3. **Keep running subagents visible; preserve history/output/logs** — **PASS**. History retains output, agent, description, prompt, timestamps; `/api/subagent-output` falls back to history; `/api/steer` resolves captured sessions; emitted log lines never removed.
4. **Consecutive tickets without reload; no carry-over** — **PASS**. Per-attempt reset before reading `stream_events(..., attempt=True)` events; current-stream entries untouched; reset state saved once.
5. **Two concurrent subagents; only the finished one is removed** — **PASS**. Covered by focused green run (112 tests OK).
6. **Regression coverage for consecutive runs and cleanup after success/failure/cancel** — **PASS**. `tests/unit/test_gh104_subagent_cleanup.py`, `tests/unit/test_output_view_runner.py` (AK4), `tests/unit/test_output_view_api.py`; tester-updated `tests/unit/test_harness.py` / `tests/unit/test_session_continue.py` expectations aligned to the `history` contract.

## Findings

- **Required fixes:** none.
- **Optional findings / minor:**
  - Minor (informational): the final full run exited 7 rather than `BASELINE-OK`; fully explained by the pre-existing signatures and stale committed baseline entries. No package action required; canonical baseline update requires a reviewed merge. Not blocking.
  - Minor decision (manifest `dateien`): **not blocking** — the manifest convention lists only manifest-scope program files; the coordinator intends to leave `docs/import-manifest.json` unchanged, and the reviewer concurs.

## The final full-run section (this evidence update)

- Run: `bash scripts/verify.sh full --env pi-aarch64-py3.14-namespaces` → exit 7.
- Totals: 2753 tests, 63/78 modules bestanden, 15 fehlgeschlagen.
- 12 × `Bekannt rot`; 3 × `Neue Regression` with the recorded signatures above; all three proven pre-existing via start-commit equality; causes are content checks of untouched files.
- No baseline/config change; no gate weakening; no canonical baseline write (prohibited in package scope).
- Environmental failure excluded from the signature comparison.

## Reviewed change set and verification limits

- Change set reviewed: `bin/vibe_runs.py`, `bin/vibe-web.py`, GH-104 tests, `docs/features/GH-104.md`, related feature/review docs; start commit `ffa0058`.
- Limits: shell execution was denied during this review session, so the reviewer did not independently re-run Git diffs or the suites; quoted check output was supplied by the tester/coordinator and is distinguished from the reviewer's own results; the failure-signature implementation was reviewed in `scripts/verify_engine.py`.

## Trillium documentation status

- Existing page `cEz7JVqNUcXx` („GH-104 — Verwaiste Subagenten aus der aktiven Ausgabe entfernt") was found and read back; German content covering realized scope and verification was confirmed; final-evidence section was appended. Status: verified; no unverified write required.

## Verdict

Verdict: PASS
