# Troubleshooting

Vibe provides diagnostics to detect problems early and provide concrete, copyable remediation steps.

## Review diagnostics

Diagnostics distinguish:

- Application prerequisites
- Optional project tools
- Host/container mismatches
- Write permissions
- Port availability
- Required programs

Missing optional components must not silently break core functionality.

## Common issues

| Issue | Possible cause | Next step |
|---|---|---|
| Dashboard is unreachable | Vibe is not running or the port is occupied | Review diagnostics and port availability |
| Agent run does not start | Missing verification configuration or a harness issue | Review verification configuration and harness logs |
| MCP connection fails | Missing executable, timeout, DNS/TLS, HTTP, authentication, or protocol error | Run a connection check and review the error class |
| Model is unavailable | The model is listed but the user is not authorized | Review provider access and credentials |
| Ticket cannot be completed | Acceptance criteria or evidence are missing | Add acceptance criteria and verification evidence |
| Update overwrites settings | Not expected; personal settings must be preserved | Review backups and report an issue |

## Logs

Vibe provides live logs and separate verification logs. These help you trace agent runs, verification, and failures independently.

## Agent runs

- Quota and login failures stop a run immediately.
- Retry limits apply only to other, repeatable error classes.
- External signals such as `HUP`, `TERM`, or `INT` produce a trace, a log entry, and an update to the run registry state.

## MCP errors

A successful connection check does not establish that an agent may use every listed tool. Agent-specific permissions must be visible or traceable.

## Safe troubleshooting

- Test changes in a separate instance before touching the production installation.
- Do not update the running instance during an agent run.
- Create a backup before migration or risky changes.
- Do not share tokens, API keys, or other secrets in issues, logs, or screenshots.
