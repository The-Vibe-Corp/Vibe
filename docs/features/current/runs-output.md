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
- Quota and login failures stop the run by default. The global setting
  `vibe limits stop|continue` in `<state>/limits.json` applies to all projects;
  a missing or invalid value means `stop`.
- `vibe sessions resume <project> --session <id> | --last | --aborted` starts a
  run with the recorded harness session after validating the ID (`AP19`, `F25`).

## Questions and subagents

- `vibe ask`, `vibe questions`, and `vibe answer` manage question records. The
  dashboard mirrors them at `/api/questions` as a banner, header counter, bell
  entry, and mailbox in the right-side panel; answers are inline and require no
  page reload (`F16`). Autonomous mode lets the agent decide and document it.
- `task`/`subagent` events from opencode are captured per child session into
  `<log>.state.json`, with a 64 KiB output tail per entry and at most 50
  entries (`B11`, `B12`).
- `/api/subagents` returns the compact list, `/api/subagent-output` the fuller
  output, and `/api/stream` the live events. `/api/steer` sends an instruction
  to the opencode session prompt using Basic Auth (`F19`).

## Output view

The output tab shows the live log with syntax highlighting and agent tabs. Main
log and subagent cards can be focused or enlarged, `Escape` clears focus, and
autoscroll follows until the user scrolls away (`AP14`, `AP16`, `AP20`, `B20`,
`F30`).

## Entry points

- CLI: `vibe run`, `attach`, `logs`, `stop`, `pause`, `runs`, `sessions`,
  `ask`, `answer`, `questions`.
- HTTP: `/api/run`, `/api/stop`, `/api/run-state`, `/api/subagents`,
  `/api/subagent-output`, `/api/steer`, `/api/questions`, `/api/sessions`, `/api/stream`.
- Files: `<runtime>/runs.json`, `<runtime>/sessions.json`,
  `<runtime>/worktrees.json`, `<runtime>/<run-key>.log`, `<log>.state.json`.

## Records

- Output view and subagents: [AP14](../AP14.md), [AP16](../AP16.md),
  [AP20](../AP20.md), [B11](../B11.md), [B12](../B12.md), [B13](../B13.md),
  [B14](../B14.md), [B20](../B20.md), [F19](../F19.md), [F24](../F24.md),
  [F30](../F30.md), [F32](../F32.md).
- Run registry, sessions, and questions: [V-015](../V-015.md),
  [V-016](../V-016.md), [V-024](../V-024.md), [V-026](../V-026.md),
  [F10](../F10.md), [AP19](../AP19.md), [F16](../F16.md).
