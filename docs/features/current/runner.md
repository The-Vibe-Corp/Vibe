# Runner and package flow

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

The runner takes one package at a time through preflight, isolated execution,
verification, review, and integration. Handoff and closure are separate steps.

## Preflight

- The project is the root of a Git repository, `HEAD` is not detached, and the
  working tree is clean; a deliberate reattach may relax the clean-tree check.
- A tester and a reviewer are configured and their agent files exist.
- `VERIFY_PACKAGE` or `VERIFY_FULL` in `.vibe/project.env` is a real command, not empty or `TODO`.
- Findings stop the start or become a question, depending on the selected mode.

## Worktree and transport

- Each package runs in its own worktree under `$VIBE_RUNTIME/worktrees` on a
  branch from `PACKAGE_BASE`; the default pattern is `feature/<owner>/<id>`,
  configurable with `PACKAGE_BRANCH_PATTERN`. A reconnect reuses a registered worktree and branch.
- `.vibe/project.env` is copied read-only (`0444`) and never written back;
  `TICKET-<ID>.json` is the visible runtime ticket copy.
- `AGENTS.md` is copied as a working note unless the project copy has
  uncommitted changes; then the package uses the committed version.

## Gate

The gate reads `TICKET-<ID>.json` and requires:

- `state` = `done`, a non-empty `test` field, and a commit present in the
  repository (or a package already merged into the base);
- `docs/features/<ID>.md` and the newest `docs/reviews/<ID>-review*.md` with
  `Verdict: PASS`;
- a clean package working copy.

## Failure handling

- Quota and authentication failures always stop the run immediately. The
  former global `vibe limits stop|continue` setting was removed; a legacy
  `<state>/limits.json` is ignored and cannot change run behaviour (GH-99).
- Network and other tool failures are retried up to `MAX_RETRIES`.
- Gate repair rounds are limited by `GATE_REPAIR_ROUNDS`; an exhausted budget
  blocks or skips the package instead of looping forever.

## Integration

- Local mode fast-forwards the accepted branch into the integration branch,
  then removes the worktree and branch. Blocked packages keep their copies.
- GitHub mode runs `github-pull` (fetch plus fast-forward only) before the
  package, `github-complete` to push and open a PR, and `ensure-mergeable` to
  merge the base into the package branch with one repair round.
- With `GITHUB_AUTO_MERGE=1` the runner squash-merges the approved PR; without
  it the package becomes `waiting-merge` and the owner closes it with
  `vibe package close`.
- The runner validates evidence and updates the store; closure is not implied by a successful agent turn.

## Autonomous mode

In autonomous mode questions are impossible; mode switches and skipped packages
are recorded as autonomous decisions.

## Discrepancy note

AP05.md's branch pattern and `TICKETS.md` gate are historical; the worktree, ticket-file, and review rules above are current.

## Entry points

- CLI: `vibe run`, `vibe attach`, `vibe logs`, `vibe stop`, `vibe pause`,
  `vibe runs`, `vibe autonomous on|off|status`, `vibe package close`.
- Script: `bin/vibe-run.sh`. HTTP: `/api/run`, `/api/questions`, `/api/autonomous`.

## Records

- [AP4-Korbat](../AP4-Korbat.md) — GitHub project completion; [AP05](../AP05.md) — clean package handling
- [AP10](../AP10.md) — gate settings; [B3-wartet-auf-merge](../B3-wartet-auf-merge.md) — waiting after merge
- [B5](../B5.md) — closing on conflict; [B6-statusmarken](../B6-statusmarken.md) — status markers
- [B9](../B9.md) — repairing blocked packages; [F4](../F4.md) — stop after current package
- [F22](../F22.md) — questions on failed preflight; [F27](../F27.md) — resume despite changes; [GH-58](../GH-58.md) — autonomous setting honored
- [V-022](../V-022.md) — Git order rule; [V-023](../V-023.md) — merged packages recognized; [V-027](../V-027.md) — former limit behavior (removed by GH-99)
- [GH-99](../GH-99.md) — package-owned sessions and costs; run-behaviour removal
