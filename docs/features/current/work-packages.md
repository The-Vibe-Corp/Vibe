# Work packages, feedback, and the ticket store

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

Tickets, work packages, bugs, and feedback share one local store per project.
The store is not versioned and is the single source for the runner and the
web interface.

## Store

- Path: `<project>/.vibe/tickets.json`. The document has `version` = 1 and a
  `tickets` list; unknown document keys are preserved.
- Writes are atomic and use an expected digest, so concurrent changes are
  detected and retried rather than silently merged (`bin/vibe_tickets.py`).
- States: `draft`, `open`, `in-progress`, `blocked`, `waiting-merge`, `done`.
- Types: `task`, `bug`, `feature`, `feedback`.
- Automatic IDs: `task` and `feature` share the `AP<n>` counter, `bug` uses
  `B<n>`, `feedback` uses `F<n>`. Allocation retries on collision.

## Validation and protected records

- `normalize()` enforces the closed state and type sets and the done
  invariant: a done ticket needs a non-empty `test` plus a `commit` or a
  `github` reference.
- Done tickets are protected from title/description edits and from deletion.
  A human may still close a ticket without proof through the explicit
  `close()` path.
- `mark-start`, `mark-blocked`, and `mark-waiting-merge` are idempotent. The
  only automatic transition is `open` → `in-progress` when a package starts.

## Working copy and handoff

Each package worktree carries a runtime copy `TICKET-<ID>.json` and an
`AGENTS.md` note. Both are runtime state and are not committed. When a package
finishes, `sync_ticket` copies `state`, `commit`, `test`, and `pr_url` from the
working copy into the store only if the record is complete and the commit
exists.

## Selection order

- `PACKAGE_ORDER` in `.vibe/project.env` is binding first.
- Otherwise candidates (`open` and `in-progress`) are sorted by priority
  `P0`–`P8` (unset last), then by position in the store.
- A package is only selected when all known dependencies are `done`.
- `github_deletions` records issue numbers to close on the next GitHub sync.

## Discrepancy note

AP05.md's `TICKETS.md`/`FEEDBACK.md` gate and B6-statusmarken.md's marker
states are historical; the machine-readable store and its states above are
current.

## Entry points

- CLI: `vibe feedback`, `vibe priority`, `vibe package close`.
- Package helpers in `bin/vibe_packages.py`: `select`, `preflight`, `gate`,
  `status`, `mark-start`, `mark-blocked`, `mark-waiting-merge`, `sync-ticket`.
- Web: Nova work board at `#/project/<name>/work`; `/api/ticket`,
  `/api/feedback`, `/api/priority`.

## Records

- [F1](../F1.md) — feedback capture with title and description
- [F8](../F8.md) — hide and protect completed feedback
- [F15](../F15.md) — work packages and bugs from the UI
- [F23](../F23.md) — automatic work-package IDs
- [F29](../F29.md) — save and follow prioritization
- [AP11](../AP11.md) — ordering of package processing
- [GH-48](../GH-48.md) — unified machine-readable ticket store
- [V-009](../V-009.md) — stable ticket and feedback processing
- [B1-ticketlogik](../B1-ticketlogik.md) — ticket logic cleanup
- [worknotes-nachweis-sync](../worknotes-nachweis-sync.md) — writing the
  ticket proof back without versioning it
