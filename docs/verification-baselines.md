# Verification baselines

Run `bash scripts/verify.sh full` without flags for package acceptance. Only `full` uses baselines; `quick` and `package` do not. Report whether exit 0 means fully green or `BASELINE-OK`.

## Updating an existing baseline

Exit 7 means a failure signature is not accepted by the baseline for this environment. Fix new regressions. Before recording a failure as pre-existing, demonstrate the same signature without the package changes in the same environment, for example at the starting commit. Record the module, failure class, signature, environment, and comparison evidence in the package report.

`tests/verify-baseline.json` is the version-controlled baseline. Update entries under the matching `VERIFY_ENV` and identify the change explicitly in review. Do not use `--write-baseline` for this workflow. Remove an entry only after its module passes. Do not lower `min_tests` or include private paths, hostnames, IP addresses, or secrets.

A manifest change affects verification. Run the acceptance check against the updated manifest. A subsequent `BASELINE-OK` does not replace the comparison evidence or the review.

## First-time bootstrap

Bootstrap requires explicit authorization. Use it at most once per environment and only when neither a local nor a committed baseline exists for that environment. First establish that every proposed failure signature is pre-existing.

`bash scripts/verify.sh full --env <label> --write-baseline` creates the local, unversioned proposal `.vibe/verify-baseline`. It is not an acceptance run and does not change the verdict. Do not rewrite a local baseline that already existed when the package started.

The canonical baseline changes only through a reviewed merge. After the merge, remove any leftover local proposal for that environment: a matching local section takes precedence over the committed one.

## Environments and locations

`VERIFY_ENV` identifies the environment a baseline section belongs to. When
one label is used at two execution locations, the baseline recorded for one
does not describe the other. This happened when the integration tree (which
runs without the sandbox, different tmp roots, HOME, and load) and the
package worktree (inside the sandbox) shared the same label: failures
observed in one location were missing from the baseline of the other, and
documented pre-existing signatures were reported as new regressions.

- Keep exactly one label per execution location. The committed baseline
  (`tests/verify-baseline.json`) describes the sandbox package-worktree
  environment. A second location records its own section in the local
  `.vibe/verify-baseline` (a matching local section takes precedence over
  the committed one) or is addressed with an explicit `--env` label;
  bootstrap it once under the rules above.
- Do not extend the committed baseline with failure signatures that only
  occur at the second location; they would mask real progress for the
  canonical environment.
- Prefer location-independent tests: no absolute paths, hostnames, or
  sandbox-only assumptions in expectations, and subprocess work with
  explicit timeouts, so a loaded parallel full run cannot turn a slow module
  into an unparsable "unknown" failure.

## Other verification failures

Exit 3 indicates a configuration error; check the invocation, baseline validity, and minimum test count. Exit 6 indicates missing test evidence. Do not suppress either error by weakening the check or making a verification command invoke itself.
