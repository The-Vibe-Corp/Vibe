# GitHub integration

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

GitHub is optional per project: when enabled, Vibe clones repositories, moves
branches, prepares merge requests, and synchronizes issues with the ticket store.

## Configuration and clone

- `GITHUB_ENABLED`, `GITHUB_REPO`, `GITHUB_API`, `GITHUB_BASE`,
  `GITHUB_AUTO_MERGE`, and the `GITHUB_ISSUES_*` keys live in
  `<project>/.vibe/project.env`; without an enabled link and `origin`, GitHub
  behaviour is deliberately skipped.
- `vibe clone <url> [name] [--branch <branch>]` checks out the repository,
  adopts it with the local template defaults, and records a github.com
  repository as enabled with its owner/name (`AP8`).

## Tokens

- Precedence for credentials is environment `GITHUB_TOKEN`/`GH_TOKEN`, then the
  project token, then the legacy global token.
- A project token is stored encrypted under
  `<state>/github-tokens/<project-digest>.json`; the master key is
  `<state>/github-token.key`. Encryption uses scrypt, an HMAC stream, and
  encrypt-then-MAC from the standard library; permissions are 0600 best effort.
- Stored tokens are sent only to `api.github.com` and `github.com` Git URLs,
  never to a configured third-party host. Tokens are masked in logs and errors.

## Status and branch operations

- `vibe github status` shows the remote and REST view. `connection()` uses
  `ls-remote` and a REST `GET` without merging or pushing; it returns findings
  instead of raising.
- `branches`, `fetch`, `pull`, `push [branch]`, and `checkout <branch>` cover
  branch work. Push sets the upstream and supports a target refspec
  `<branch>:<target>`; checkout refuses uncommitted changes and branches held by
  another worktree.
- `pr` creates a merge request only with explicit confirmation. `test` checks
  the configured connections; `link`/`unlink` manage the remote.

## Runner integration

- Before a package, `pull_integration` fetches `origin` and fast-forwards the
  integration branch. It creates no merge commits and never raises.
- On package completion, `integration_state` blocks a stale or diverged branch
  before anything is pushed. `complete_package` then pushes the package branch
  and creates a merge request against the configured base (`B16`).
- With `GITHUB_AUTO_MERGE=1`, the runner may squash-merge the approved request
  through the REST API; otherwise the request stays open for the owner.

## Issues

- `vibe github issues-sync` performs one bidirectional sync (`GH-47`). It
  imports new issues, maps labels to local states (`ready` becomes `open`), and
  pushes changes back for runnable tickets. Deleting a linked ticket closes the
  issue on a best-effort basis and records a tombstone.
- Done tickets are not reopened by remote labels. In status reporting, a
  package with completed proof is reported as done rather than blocked or
  waiting for merge (`B3-wartet-auf-merge`).

## Discrepancy note

`AP05.md`'s local-mode merge description belongs to the runner flow, described
in [Runner and package flow](runner.md), not to GitHub mode.

## Entry points

- CLI: `vibe clone`, `vibe github status|token|link|branches|fetch|pull|push|checkout|test|issues-sync|pr`.
- HTTP: `/api/clone`, `/api/github`.
- Files: `<project>/.vibe/project.env`, `<state>/github-tokens/`,
  `<state>/github-token.key`.

## Records

- Clone, connection, and preparation: [AP6](../AP6.md), [AP8](../AP8.md),
  [AP12](../AP12.md), [B8](../B8.md).
- Tokens and authentication: [AP9](../AP9.md), [B7](../B7.md).
- Finished packages: [B16](../B16.md).
- Issues: [AP3-Korbat](../AP3-Korbat.md), [GH-47](../GH-47.md).
