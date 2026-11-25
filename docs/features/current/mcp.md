# MCP servers

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

Vibe manages Model Context Protocol servers in the opencode configuration
files. Server definitions are read and written in the file that opencode
itself would use first.

## Configuration files

Candidates are checked in this order and the first existing file wins:

1. `opencode.json`
2. `opencode.jsonc`
3. `.opencode/opencode.json`
4. `.opencode/opencode.jsonc`

The global base is `~/.config/opencode`; a project's base is its root. If none
exists, the first candidate is created when a server is written. The layout is
detected as `servers`, `classic`, or `unknown` from the file contents and the
installed opencode capability information.

## Schema

The schema follows opencode 2.1.4:

- local: `type`, `command`, `cwd`, `environment`, `enabled`, `timeout`;
- remote: `type`, `url`, `enabled`, `headers`, `oauth`, `timeout`.

Fields not supported by the installed version are not offered.

## Editing

- Writes preserve JSONC formatting and comments around the edited member. Only
  the changed server entry is replaced.
- When the server type does not change, unknown fields of the existing entry
  are preserved.
- Secrets in `environment`, `headers`, `url`, and `oauth.clientSecret` are
  masked as `***` in listings and responses. On save, masked values are
  restored from the previous entry; a value that cannot be restored
  unambiguously is rejected.
- Backups are written with an expected digest, so a concurrent external change
  is detected instead of overwritten.

## Connection test

- The test only performs the MCP `initialize` handshake and `tools/list`. It
  never invokes a functional tool.
- Local servers are started over stdio; remote servers use Streamable HTTP.
- Limits: timeout 5–90 s for local and 5–60 s for remote, at most 200 tools,
  4 MiB over stdio, 1 MiB over HTTP.
- Test processes are stopped as a process group, including children.
- The result distinguishes missing executable, timeout, DNS/TLS, HTTP,
  authentication, protocol, and invalid-configuration failures.

## Discrepancy note

V-013.md and V-014.md match the tested opencode 2.1.4 behavior; no material
discrepancy was found.

## Entry points

- CLI: `vibe mcp list|show|test|on|off|rm|backups|restore [name]
  [global|<project>]`.
- HTTP: `/api/mcp`, `/api/mcp_entry`.

## Records

- [V-007](../V-007.md) — opencode compatibility adapter
- [V-013](../V-013.md) — lossless MCP configuration editing
- [V-014](../V-014.md) — robust and bounded MCP connection tests
