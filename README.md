<div align="center">

# Vibe

**The local development hub for AI-assisted software projects.**

Vibe brings projects, agents, models, MCP servers, agent runs, verification, and diagnostics together in a locally hosted web interface and CLI.

[![License](https://img.shields.io/github/license/The-Vibe-Corp/Vibe?style=flat-square)](./LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-blue?style=flat-square)](docs/INSTALLATION.md)
[![Contributing](https://img.shields.io/badge/contributions-welcome-brightgreen?style=flat-square)](./CONTRIBUTING.md)
[![Security](https://img.shields.io/badge/security-policy-available-informational?style=flat-square)](./SECURITY.md)

[Features](#features) ·
[Quick start](#quick-start) ·
[Documentation](#documentation) ·
[Architecture](#architecture) ·
[Contributing](#contributing)

</div>

---

## What is Vibe?

Vibe is a **local development hub** for AI-assisted software projects. Instead of managing agents, models, MCP servers, tickets, logs, and verification across separate tools, Vibe brings these building blocks into one organized workspace.

Vibe is **not an AI harness**. It works with external, interchangeable harnesses through isolated execution and configuration interfaces. OpenCode is a supported harness.

Vibe is designed for consultants, product owners, project managers, and anyone who wants to build reliable software without needing deep development expertise. Users describe goals, requirements, and feedback, while technical configuration, agent runs, and verification remain visible and controllable.

## Features

| Area | What Vibe provides |
|---|---|
| **Projects** | Manage development directories, recognize projects through Git metadata or Vibe configuration, and show status, branch, changes, open work packages, run status, and the latest commit. |
| **Work packages** | Manage tickets, bugs, feedback, and work packages locally, including status, acceptance criteria, evidence, and integration. |
| **Agents** | Create, edit, copy, and delete global and project-specific agents, and assign them through configurable roles. |
| **Models** | Manage and assess models from multiple providers and assign them to roles through model profiles. |
| **MCP servers** | Manage local and remote MCP servers, test connections, and inspect available tools. |
| **Agent runs** | Start, observe, attach to, selectively stop, and run agents concurrently across projects. |
| **Verification** | Configure package and integration verification as separate gates and document supporting evidence. |
| **Diagnostics** | Check operating system, containers, Python version, ports, write permissions, and optional tools. |
| **Local first** | Source code, installation, and runtime data remain separate; users retain control of local data, credentials, and project sources. |

These capabilities follow the binding product specification in [`SPEC.md`](./SPEC.md).

## Quick start

### Prerequisites

- A Python environment
- Linux, Windows, or macOS
- Optional: Docker, Podman, Toolbx, or Distrobox for containerized environments
- Optional: Git for project-related workflows

Vibe determines actual support through diagnostics. It distinguishes mandatory application prerequisites from optional project tools; missing optional components must not silently break core functionality.

### Install on Linux

The Linux entry point is `install-vibe.sh`. It requires the `VIBE` environment variable to point to your Vibe workspace and invokes the cross-platform setup script, `scripts/setup-vibe.py`. [cite:2]

```bash
VIBE=/path/to/your/vibe-workspace bash install-vibe.sh
```

The script installs or updates Vibe without prompts and uses the current repository as its source. [cite:2]

### Install on Windows

Vibe includes a dedicated Windows entry point:

```powershell
.\setup-vibe.cmd
```

For workspace paths, containers, updates, and rollback behavior, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

### Open the dashboard

After starting Vibe, open the local dashboard in your browser. By default, the web server binds to loopback; an explicitly configured network bind address must be an IP literal, not a DNS hostname.

## Documentation

| Document | Contents |
|---|---|
| [Installation](docs/INSTALLATION.md) | Installation, updates, workspace, Windows, Linux, and containers |
| [Configuration](docs/CONFIGURATION.md) | Workspace, runtime data, projects, profiles, and migration |
| [Agents](docs/AGENTS.md) | Global and project agents, roles, permissions, prompts, and runs |
| [Models](docs/MODELS.md) | Providers, model profiles, pricing, availability, and assessment principles |
| [MCP servers](docs/MCP.md) | Local and remote MCP servers, connection checks, transports, and secrets |
| [Workflows](docs/WORKFLOWS.md) | Tickets, work packages, agent runs, verification, and integration |
| [Development](docs/DEVELOPMENT.md) | Repository structure, tests, quality criteria, and contributions |
| [Security](docs/SECURITY.md) | Local data ownership, authentication, secrets, sandboxing, and auditing |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Diagnostics, common issues, logs, and safe remediation |

## Architecture

Vibe deliberately separates **project source code**, **installation**, and **runtime data**. Updating one layer must not overwrite the others.

```text
Project sources ──► Vibe workspace ──► Agent runs ──► Verification ──► Integration
       │                 │                │                │                 │
       └── Git / files   └── Configuration └── Harness      └── Evidence      └── Merge / PR
```

Core concepts:

| Term | Meaning |
|---|---|
| **Project source** | Source code in a Git repository |
| **Installation** | The deployed, executable Vibe application |
| **Runtime data** | Settings, logs, tokens, backups, and status records |
| **Global agent** | An agent available to all projects |
| **Project agent** | An agent available only within one project |
| **MCP server** | A service that provides tools through MCP |
| **Model profile** | A mapping of models to roles |
| **Agent run** | Execution of a work package through a harness supported by Vibe |
| **Dashboard** | The Vibe web application |
| **Runner** | The Vibe-managed process that coordinates work packages, Git workspaces, verification, and closing actions |

These definitions come from the product specification.

## Workflows

Vibe coordinates the path from an idea to an integrated change:

1. **Register a project** — Add a development directory or recognize an existing project.
2. **Capture a requirement** — Create feedback, a bug report, or a work package.
3. **Select agents** — Assign appropriate coder and reviewer agents through roles.
4. **Start execution** — Run the work package through a supported harness.
5. **Review the result** — Inspect live logs, verification logs, and supporting evidence.
6. **Complete integration** — Merge locally or create a GitHub pull request when configured.

A commit alone does not prove acceptance: completing a work package requires satisfied acceptance criteria and appropriate supporting evidence.

## Security and data ownership

Vibe is local-first. The web server binds to loopback by default, authenticated mutating API requests are required, and tokens must never appear in access logs or error messages.

Key principles:

- Users retain control of local data, credentials, and project source code.
- Security-sensitive actions are visible, subject to limits, and recorded in auditable logs.
- Credentials do not belong in agent files or this repository.
- Project check commands and MCP programs are treated as trusted-code execution.
- Files are written atomically, and concurrent changes are detected.
- API keys, tokens, global configurations, and personal agents are never automatically added to Git.

See [docs/SECURITY.md](docs/SECURITY.md) and [`SECURITY.md`](./SECURITY.md) for details.

## Project structure

```text
Vibe/
├── .github/               # GitHub configuration and workflows
├── bin/                   # Executable entry points
├── data/                  # Static or bundled data
├── docs/                  # Project and user documentation
├── scripts/               # Setup, maintenance, and helper scripts
├── templates/             # Project and configuration templates
├── tests/                 # Unit, integration, and browser tests
├── install-vibe.sh        # Linux entry point for installation and updates
├── setup-vibe.cmd         # Windows entry point
├── SPEC.md                # Binding product specification
├── CONTRIBUTING.md        # Contribution guidelines
├── SECURITY.md            # Security policy
├── CODE_OF_CONDUCT.md     # Code of conduct
└── LICENSE                # License, including the commercial-use exception
```

This structure reflects the current repository contents. [cite:0]

## Development

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
```

Vibe follows an incremental decoupling approach: the CLI and web API remain thin, domain logic is shared through services, file access is placed behind testable storage functions, and static frontend files remain separate from Python code.

Quality is supported by unit tests for domain logic, integration tests for APIs, storage, and process adapters, and browser tests for core workflows. Mocks do not replace browser or system acceptance checks.

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) and [`CONTRIBUTING.md`](./CONTRIBUTING.md) for details.

## Contributing

Contributions are welcome. Keep changes focused, clearly describe the problem they solve, and provide appropriate functional and technical evidence.

1. Fork the repository.
2. Create a branch: `git checkout -b feature/my-feature`.
3. Implement the change, including suitable tests.
4. Run the relevant tests and verification.
5. Open a pull request with a clear description and evidence.

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full guidelines.

## Support

- **Bugs and feature requests:** [GitHub Issues](https://github.com/The-Vibe-Corp/Vibe/issues)
- **Security reports:** See [`SECURITY.md`](./SECURITY.md)
- **Code of conduct:** [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)

## License

Vibe is licensed under the terms contained in [`LICENSE`](./LICENSE).

The license file remains unchanged and includes the existing exception for commercial use. For the binding license text and the exact terms and limits of that exception, see [`LICENSE`](./LICENSE).

---

<div align="center">

**Vibe** — Local control for AI-assisted software development.

</div>
