# Verification and checks

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

Project verification runs in an isolated temporary environment. Checks are
configured per project in `.vibe/project.env`; agents may run them but must not
replace the configured gate commands.

## Entry point and modes

- `bash scripts/verify.sh quick|package|full` is the single interface. The
  script checks for `python3` and `exec`s `scripts/verify_engine.py`, which owns
  all logic (`AP7-Korbat`).
- `quick` runs `VERIFY_QUICK`. In this repository that is
  `scripts/check-import-manifest.py`, `scripts/check-syntax.py`, and
  `scripts/check-no-secrets.py`.
- `package` runs `quick` and then `VERIFY_PACKAGE_TESTS` when configured. A
  missing test structure is an error, not a pass.
- `full` runs the unit tests from `VERIFY_TESTS` through
  `scripts/run-tests-parallel.py` and compares failures with the baseline.
  Only `full` uses a baseline.
- `VERIFY_PACKAGE` and `VERIFY_FULL` are wrapper commands used by the runner,
  not additional command variables read by the engine.

## Isolation and guards

- A dedicated temporary directory holds `HOME`, `VIBE`, `TMPDIR`, and the XDG
  directories. Dedicated free ports are provided for the dashboard, opencode,
  tests, and the check itself.
- An inherited `TMUX` is removed and `TMUX_TMPDIR` points into the temporary
  directory, so a test cannot stop the caller's tmux server.
- A self-path guard rejects a `VERIFY_QUICK` token that resolves to
  `verify.sh`, `verify.py`, or `verify_engine.py`. The depth guard rejects
  `VIBE_VERIFY_DEPTH >= 2`. Both end with exit 3.

## Baseline and exit codes

- `tests/verify-baseline.json` currently sets `min_tests` to 2500 and the
  environment `pi-aarch64-py3.14-namespaces`. A lower `min_tests` is rejected.
- Exit 0 means green, or `BASELINE-OK` when remaining failures match recorded
  signatures. Exit 3 is a configuration error, 6 missing test proof, and 7 a
  failure not accepted by the baseline. Exit 4 means a required tool is missing
  and 5 an unevaluable check command.
- Baseline comparisons, updates, and exceptions are described in
  `docs/verification-baselines.md`.

## Browser tests

Browser tests live under `tests/browser/` and run separately from the `full`
mode, typically through `scripts/run-tests-parallel.py --dir tests/browser`.
They are not part of the unit-test baseline comparison.

## Discrepancy note

Some historical records name `scripts/verify.py` as the entry point; it is now
a compatibility shim that delegates to `scripts/verify_engine.py`.

## Entry points

- CLI: `bash scripts/verify.sh quick|package|full`, with options such as
  `--project`, `--tests`, `--jobs`, `--timeout`, `--baseline`, `--env`,
  `--min-tests`, and `--write-baseline`.
- Checks: `scripts/check-import-manifest.py`, `scripts/check-syntax.py`,
  `scripts/check-no-secrets.py`; runner: `scripts/run-tests-parallel.py`.
- Files: `<project>/.vibe/project.env`, `tests/verify-baseline.json`.

## Records

- [AP5-Korbat](../AP5-Korbat.md) — clean artifacts and improve checks
- [AP6-Korbat](../AP6-Korbat.md) — unit-test hygiene cleanup
- [AP7-Korbat](../AP7-Korbat.md) — rework `verify.sh` logic
- [B17](../B17.md) — verification must not touch the running instance
- [GH-46](../GH-46.md) — fix the new testing logic
- [GH-80](../GH-80.md) — integration-branch test regression
- [V-001](../V-001.md) — capture and secure the unchanged inventory
- [V-002](../V-002.md) — secure development and test environment
- [verify-tmux-isolation](../verify-tmux-isolation.md) — caller's tmux stays untouched
