# Agent runs and the output view

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

A run executes a work package through the selected harness in tmux and is recorded for CLI and dashboard control.

## Registry and lifecycle

- `vibe run <project> [agent]` starts a detached tmux session running the
  package runner. The session ends when the runner exits (`F10`).
- A run ID is `<run-key>-YYYYMMDD-HHMMSS-<six hex characters>`. Colliding
  normalized project names receive a path fingerprint (`bin/vibe_runs.py`).
- `<runtime>/runs.json` keeps the last 100 entries. States are `starting`,
  `running`, `finished`, `stopped`, `paused`, `failed`, `ended`, and `blocked`;
  `ended` means an unexpected end and is displayed as aborted.
- `<runtime>/sessions.json` records harness sessions with a default limit of 5,
  a maximum of 100, and per-project overrides; `<runtime>/worktrees.json` tracks
  package worktrees, with a lock file serializing writes.
- The work package is the owner of a session assignment: valid harness session
  IDs are stored in `sessions` on the package record in
  `<project>/.vibe/tickets.json`, never derived from a display name. A session
  belongs to exactly one package of exactly one project; multiple sessions per
  package are allowed (GH-99).

## Control

- `vibe attach` joins the live session, `vibe logs` follows the run log, and
  each run also has a separate `.verify.log`. `vibe stop <project> [run-id]`
  stops only the selected Vibe-managed session, or the latest live run.
- `vibe pause <project> on` writes `<runtime>/<run-key>.pause-after`. The runner
  finishes the current package and starts no new one; the marker is one-shot.

## Recovery, limits, and resume

- Before a run starts, live entries of that project whose tmux session is gone
  are marked `ended` with the note `extern beendet (Sitzung fehlt)`; other
  projects and unverifiable sessions stay untouched (`V-026`). `vibe runs prune`
  does the same on demand and never kills a session.
- An external `HUP`, `TERM`, or `INT` is logged with the signal and leaves an
  `ended` registry state.
- Quota and login failures always stop the run immediately. The former global
  `vibe limits stop|continue` setting was removed; a legacy `limits.json` is
  ignored and cannot change run behaviour (GH-99).
- `vibe sessions resume <project> --session <id> | --last | --aborted` starts a
  run with the recorded harness session after validating the ID (`AP19`, `F25`).
- A run without an explicit resume request reuses the stored session of its
  work package when one exists (`vibe sessions for-package`). A new session is
  created only when no stored session can be continued or a restart was
  requested explicitly (GH-99).
- On successful completion of a work package, its usage is flushed to persisted
  package costs first, then all assigned sessions and their assignments are
  removed. Pause, abort and failed runs never trigger this cleanup (GH-99).

## Questions and subagents

- `vibe ask`, `vibe questions`, and `vibe answer` manage question records. The
  dashboard mirrors them at `/api/questions` as a banner, header counter, bell
  entry, and mailbox in the right-side panel; answers are inline and require no
  page reload (`F16`). Autonomous mode lets the agent decide and document it.
- `task`/`subagent` events from opencode are captured per child session into
  `<log>.state.json`, with a 64 KiB output tail per entry (`B11`, `B12`).
- The state file keeps the lifecycle apart (GH-104): `subagents` is the
  active list only, while `history` holds retired entries with their output.
  Both lists are bounded; the history keeps the newest 50 entries.
- A subagent leaves the active list at its own terminal event
  (`completed`, `error`, `failed`, `cancelled`, `canceled`), including
  opencode background subagents whose metadata status ends the run and Pi
  `tool_execution_end` events. The retired entry moves to `history`
  immediately, so other concurrent subagents stay active. At the start of a
  new attempt in the same run, any leftover active entry from an earlier
  ticket is retired first; entries created within the current attempt are
  untouched.
- Later events of a retired child session revive that entry from `history`
  (`status=running`, `ended=0`) with its accumulated output intact. Sibling
  entries are not revived. Emitted log lines are never removed.
- `/api/subagents` returns only active entries; `/api/subagent-output`
  returns the fuller output and also finds retired entries in `history` so
  their stored output stays retrievable. `/api/steer` sends an instruction to
  the opencode session prompt using Basic Auth (`F19`) and keeps resolving
  captured subagent sessions. `/api/stream` carries the live events.

## Output view

The output tab shows the live log with syntax highlighting and agent tabs. Main
log and subagent cards can be focused or enlarged, `Escape` clears focus, and
autoscroll follows until the user scrolls away (`AP14`, `AP16`, `AP20`, `B20`,
`F30`). In the Nova view the user's scroll position is held steady while new
lines arrive; following resumes only when the user scrolls back to the end
(`GH-88`).

Nova arranges the output in two responsive grids styled with the shared design
tokens: the compact overview at the top and the large windows below (`GH-100`).
In the overview each agent row wraps inside its grid cell, and the column count
drops before a row falls below its readable minimum; the strip never scrolls
horizontally. Each main-agent window occupies its own full-width row; only
subagent windows share the grid below it, keeping the established 24rem
minimum per column. Both grids use the available width without a horizontal
scrollbar, and narrow views fall back to a single column with wrapped content.

Every large output window has a definite height that changes only at layout
breakpoints and never grows with the amount of output; long output scrolls
vertically inside its window. Focus and “Alles anzeigen” still lift the fixed
height for the enlarged or fully expanded view. The redundant
“läuft / Hauptagent / Subagenten” status row is no longer rendered (`GH-88`);
agent name and run state remain visible in the summary rows and the main card.

## Entry points

- CLI: `vibe run`, `attach`, `logs`, `stop`, `pause`, `runs`, `sessions`
  (including `attach`, `for-package`, `finish-package`, `migrate`), `ask`,
  `answer`, `questions`.
- HTTP: `/api/run`, `/api/stop`, `/api/run-state`, `/api/subagents`,
  `/api/subagent-output`, `/api/steer`, `/api/questions`, `/api/sessions`, `/api/stream`.
- Files: `<runtime>/runs.json`, `<runtime>/sessions.json`,
  `<runtime>/worktrees.json`, `<runtime>/<run-key>.log`, `<log>.state.json`.

## Records

- Output view and subagents: [AP14](../AP14.md), [AP16](../AP16.md),
  [AP20](../AP20.md), [B11](../B11.md), [B12](../B12.md), [B13](../B13.md),
  [B14](../B14.md), [B20](../B20.md), [F19](../F19.md), [F24](../F24.md),
  [F30](../F30.md), [F32](../F32.md), [GH-88](../GH-88.md),
  [GH-100](../GH-100.md), [GH-104](../GH-104.md).
- Run registry, sessions, and questions: [V-015](../V-015.md),
  [V-016](../V-016.md), [V-024](../V-024.md), [V-026](../V-026.md),
  [F10](../F10.md), [AP19](../AP19.md), [F16](../F16.md),
  [GH-99](../GH-99.md).
