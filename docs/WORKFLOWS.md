# Workflows

Vibe coordinates the path from a requirement to an integrated change: tickets, work packages, agent runs, verification, and closing actions are managed by a runner. [cite:1]

## Terms

| Term | Meaning |
|---|---|
| **Ticket** | A work package, bug, or feedback item |
| **Work package** | A scoped unit of work with a goal and acceptance criteria |
| **Agent run** | Execution of a work package through a supported harness |
| **Runner** | The Vibe-managed process for work packages, Git workspaces, verification, and closing actions |
| **Verification** | Functional validation of a package or the integration state |

These terms are part of the binding product specification. [cite:1]

## Ticket lifecycle

Tickets are stored locally, unversioned, and machine-readably in `.vibe/tickets.json`. [cite:1]

```text
draft → open → in-progress → blocked / awaiting-merge → completed
```

Users can add feedback and create, edit, or delete work packages. IDs are assigned automatically unless the user supplies one. [cite:1]

## Acceptance and evidence

A work package is complete only when:

- Acceptance criteria are satisfied.
- Appropriate supporting evidence is available.
- A commit alone does not prove acceptance.
- A blocked ticket is not complete. [cite:1]

The runner validates evidence from the ticket working copy and updates the ticket store. An agent finishing its work does not mean the package has been integrated. [cite:1]

## Package handoff and closure

Package handoff and closure are distinct steps. [cite:1]

### Local mode

In local mode, the runner merges an accepted package into the local integration branch and cleans up the package worktree and branch. [cite:1]

### GitHub mode

In GitHub mode, the runner fetches the current integration state and merges it into the feature branch before pushing. Conflicts are resolved in the package worktree. [cite:1]

## Pull requests

Without auto-merge, the runner opens a pull request and waits for manual merge and closure confirmation. The worktree remains registered in the meantime. [cite:1]

With auto-merge enabled, the runner may squash-merge an approved pull request after all gates pass. Final synchronization and cleanup follow the confirmed merge. [cite:1]

Automatic publication, push, merge, or release does not occur without authorization. Automatic GitHub merging requires a configured opt-in. [cite:1]

## Verification

Package verification and full verification of the integration state are separate runner gates. Checks are configured per project; agents cannot replace the configured gate commands during a run. [cite:1]

- Missing verification configuration is an error, not a successful check.
- Retry and iteration limits are configurable.
- An iteration limit is not a spending budget and must not be labeled as one. [cite:1]

## Failures and stops

Quota and login failures stop a run immediately. Retry limits apply only to other, repeatable error classes. [cite:1]

External signals such as `HUP`, `TERM`, or `INT` do not end a run without a trace. Vibe records the signal, a log entry, and the run registry state. [cite:1]

On startup, orphaned `running` entries for the current project are marked as externally terminated. Other projects, active sessions, and sessions whose state cannot be determined remain unchanged. [cite:1]
