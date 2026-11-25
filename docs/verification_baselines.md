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

## Other verification failures

Exit 3 indicates a configuration error; check the invocation, baseline validity, and minimum test count. Exit 6 indicates missing test evidence. Do not suppress either error by weakening the check or making a verification command invoke itself.
