# MCP servers

An **MCP server** is a service that provides tools through the Model Context Protocol. Vibe manages global and project-specific MCP servers centrally.

## Management

For MCP servers, you can:

- List servers
- Create servers
- Edit servers
- Delete servers
- Enable servers
- Disable servers

## Local servers

For local MCP servers, Vibe manages:

- The executable
- The argument list
- Environment variables

## Remote servers

For remote MCP servers, Vibe manages:

- The URL
- Headers
- Supported authentication

## Configuration protection

Vibe documents the actual configuration files and their precedence. Unknown settings and comments are preserved wherever possible.

If an edit cannot preserve a file faithfully, Vibe stops or requests approval for a concrete change preview. Data is never silently discarded.

## Secrets

Secrets are masked, but their values are preserved when saving. They are not exposed in responses, errors, command displays, or logs.

## Connection checks

Before a connection check, Vibe explains that it may start programs or open network connections. A connectivity check is not guaranteed to be side-effect free.

The check calls `initialize` and `tools/list`, displays the server identity and available tools, and does not automatically invoke functional tools.

## Error classes

Vibe distinguishes:

- Missing executables
- Timeouts
- DNS and TLS errors
- HTTP errors
- Authentication failures
- Protocol failures
- Invalid configuration

Supported transports are displayed explicitly. An unsupported transport does not mean that the server is defective.

## Resource protection

Connection checks limit execution time, output, and resource use. Test processes and their children are reliably stopped.

A successful connection check does not establish that an agent may use every listed tool. Agent-specific permissions must be visible or traceable.
