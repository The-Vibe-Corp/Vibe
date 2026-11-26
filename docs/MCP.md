# MCP servers

An **MCP server** is a service that provides tools through the Model Context Protocol. Vibe manages global and project-specific MCP servers centrally. [cite:1]

## Management

For MCP servers, you can:

- List servers
- Create servers
- Edit servers
- Delete servers
- Enable servers
- Disable servers [cite:1]

## Local servers

For local MCP servers, Vibe manages:

- The executable
- The argument list
- Environment variables [cite:1]

## Remote servers

For remote MCP servers, Vibe manages:

- The URL
- Headers
- Supported authentication [cite:1]

## Configuration protection

Vibe documents the actual configuration files and their precedence. Unknown settings and comments are preserved wherever possible. [cite:1]

If an edit cannot preserve a file faithfully, Vibe stops or requests approval for a concrete change preview. Data is never silently discarded. [cite:1]

## Secrets

Secrets are masked, but their values are preserved when saving. They are not exposed in responses, errors, command displays, or logs. [cite:1]

## Connection checks

Before a connection check, Vibe explains that it may start programs or open network connections. A connectivity check is not guaranteed to be side-effect free. [cite:1]

The check calls `initialize` and `tools/list`, displays the server identity and available tools, and does not automatically invoke functional tools. [cite:1]

## Error classes

Vibe distinguishes:

- Missing executables
- Timeouts
- DNS and TLS errors
- HTTP errors
- Authentication failures
- Protocol failures
- Invalid configuration [cite:1]

Supported transports are displayed explicitly. An unsupported transport does not mean that the server is defective. [cite:1]

## Resource protection

Connection checks limit execution time, output, and resource use. Test processes and their children are reliably stopped. [cite:1]

A successful connection check does not establish that an agent may use every listed tool. Agent-specific permissions must be visible or traceable. [cite:1]
