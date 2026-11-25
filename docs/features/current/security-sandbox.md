# Security, permissions, and sandbox

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

Vibe is a local application: access control protects the dashboard, write
permissions and gates bound agent work, and a sandbox can limit writes.

## Network binding and login

- The dashboard binds to `127.0.0.1` by default. `vibe ui --bind` accepts only
  an IP literal; DNS hostnames are rejected against rebinding. An optional
  IP/CIDR allowlist restricts clients, while loopback stays allowed.
- A start URL carries a token fragment. Alternatively, a configured dashboard
  password creates an `HttpOnly`, `SameSite=Strict` session cookie after login.
- The password is stored only as a salted PBKDF2-SHA256 hash in `ui.json`;
  `vibe ui password set|clear|status` manages it without argument input, and a
  running dashboard applies the change on the next login.

## Request protection

- Every mutable request requires authentication. `_guard` in `bin/vibe-web.py`
  checks `Host`, `Origin`, and `Sec-Fetch-Site`, which provides the CSRF
  protection. JSON bodies must be objects and are limited to 1 MiB; access logs
  omit query strings, and error messages redact the token.

## Write permissions and gates

- Each project may list allowed write directories in
  `<project>/.vibe/permissions.json`; the defaults are `/tmp/opencode` and the
  project directory. `vibe rights <project> list|add|rm|reset` manages them
  atomically. Runner barriers (Schranken) are global in `<state>/gates.json` and
  may be overridden per project with `REPAIR_ROUNDS`, `ASSIST_ROUNDS`,
  `MAX_RETRIES`, `MAX_PACKAGES`, and `GATE_OVERRIDE`; `vibe gates` shows them.

## Sandbox

- `SANDBOX=on|1|true|yes` in `.vibe/project.env` activates bubblewrap. If
  `bwrap` is missing, the run refuses to start rather than falling back
  silently.
- The root filesystem is read-only. Writes are limited to permitted project
  directories, configured caches, sandbox state, and explicitly allowed paths;
  `/tmp` is a private tmpfs made read-only, and the project's `.vibe` stays
  read-only so an agent cannot widen its permissions. Network access remains.
- This is a write boundary, not full isolation: reads are not restricted.
  `vibe sandbox <project> status|on|off|tools|check` inspects and changes it.
- Rendering agent templates preserves the configured subagent permission
  policy (`B7-subagent-permissions`).

## Secrets

- The opencode server password is generated into `<runtime>/opencode.password`.
  An inherited `OPENCODE_PASSWORD` is unset before start so it cannot override
  the managed password (`fix-opencode-password-env`).
- Project GitHub tokens are encrypted under `<state>/github-tokens/`; see
  [GitHub integration](github.md).

## Discrepancy note

SPEC requires auditable logs for security-sensitive actions; no dedicated
audit-log implementation was located, so this remains an open gap, not current behavior.

## Entry points

- CLI: `vibe ui --bind`, `vibe ui password ...`, `vibe rights`, `vibe sandbox`,
  `vibe gates`.
- HTTP: `/api/security`; protected mutable endpoints include `/api/run`,
  `/api/stop`, `/api/ticket`, and `/api/rights`.
- Files: `ui.json`, `<project>/.vibe/permissions.json`,
  `<state>/gates.json`, `<runtime>/opencode.password`.

## Records

- Access and login: [AP13](../AP13.md), [AP18](../AP18.md),
  [V-004](../V-004.md).
- Sandbox and write permissions: [AP1](../AP1.md), [F3](../F3.md),
  [F7](../F7.md), [B7-subagent-permissions](../B7-subagent-permissions.md).
- Data and process safety: [V-003](../V-003.md), [V-005](../V-005.md).
- Keys and secrets: [AP23](../AP23.md),
  [fix-opencode-password-env](../fix-opencode-password-env.md).
