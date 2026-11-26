# Security and data integrity

Vibe is local-first. Users retain control of local data, credentials, and project source code. Security-sensitive actions are visible, subject to limits, and recorded in auditable logs.

## Network and access

- The web server binds to loopback by default.
- An explicitly configured network bind address must be an IP literal; DNS hostnames are rejected to prevent DNS rebinding.
- An IP/CIDR allowlist may restrict clients; loopback remains allowed by that list.

## Authentication

Authentication uses a token or password with a session cookie rather than leaving a permanent token in the browser. Mutating API requests require valid authentication.

Host and Origin checks and CSRF protection are enforced.

## Secrets

- Tokens are never included in access logs or error messages.
- Credentials do not belong in agent files or this repository.
- Secret values are preserved when saving but are masked.
- Secrets are not exposed in responses, error messages, command displays, or logs.

## Input and file access

- Input and request sizes are limited.
- Path traversal and unauthorized symlink targets are prevented.
- External commands are invoked using argument lists rather than shell concatenation, unless explicitly configured shell execution is required.

## Trusted code

Project check commands and MCP programs are treated as **trusted-code execution**, not passive configuration.

## Files and backups

- Files are written atomically.
- Concurrent changes are detected.
- Backups do not collide and may contain sensitive data.
- Sensitive runtime data is stored on a suitably protected filesystem.
- Unix permissions are not treated as effective on FUSE or NTFS without evidence.

## Git and repository

API keys, tokens, global configurations, or personal agents are never automatically added to Git.

## Sandbox

Agents can optionally run in a sandbox to limit access to the host.

## Security reports

Do not report security issues publicly in GitHub Issues. Follow the guidance in [`SECURITY.md`](../SECURITY.md).
