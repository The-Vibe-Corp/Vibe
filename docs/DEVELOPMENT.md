# Development

Vibe is developed incrementally. The existing source code is the starting point; a complete rewrite requires an explicitly approved migration ticket.

## Clone the repository

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
```

## Target structure

The target structure separates the application, web interface, data, templates, scripts, tests, and documentation.

```text
bin/
src/vibe/
web/
data/
templates/
scripts/
tests/unit/
tests/integration/
tests/browser/
docs/
.vibe/
```

## Architecture principles

- Keep the CLI and web API thin.
- Share domain services for projects, agents, profiles, and MCP.
- Put file access behind testable repository and storage functions.
- Return structured results from business logic rather than capturing stdout.
- Keep static frontend files separate from Python code.
- Importing modules must not start servers, containers, or programs.

## Testing

Vibe uses three test layers:

| Test type | Purpose |
|---|---|
| **Unit tests** | Domain logic and validation |
| **Integration tests** | APIs, storage, and process adapters |
| **Browser tests** | Core workflows |

Mocks alone do not replace browser or system acceptance checks. Tests use temporary directories and dedicated ports, not personal projects or production configuration.

## Quality criteria

Every ticket requires functional and technical evidence and an independent review. Changed testable behavior must be demonstrated by suitable tests.

Existing tests are sufficient if they were run and demonstrate the criterion. For changes without meaningful runtime behavior, an appropriate alternative check is documented.

Verification records state the command, result, and limits of the evidence.

## Locked decisions

- Import the existing source; do not regenerate it.
- Do not mark functionality complete before it has been verified.
- Retain the local web application and CLI.
- Decouple features incrementally.
- Keep runtime data and secrets out of the repository.
- Mark unverified model information as unknown.
- Address security and data-integrity defects before convenience features.

## Contributing

Contributions follow the guidelines in [`CONTRIBUTING.md`](../CONTRIBUTING.md). Keep pull requests focused, describe the problem being solved, and provide suitable tests or evidence.
