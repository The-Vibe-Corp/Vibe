# Vibe — Product Specification

Status: Binding product specification  
Starting point: Installed Vibe v5 system and existing desktop launcher  
Web interface: English, German supported  
Project documentation and review reports: English

## Product goal

Vibe is a local development hub for AI-assisted software projects. Its web interface and CLI bring together projects, agents, models, MCP servers, agent runs, verification, and diagnostics.

Vibe is not an AI harness. It works with external, interchangeable harnesses through isolated execution and configuration interfaces. OpenCode is a supported harness.

The existing installation is the starting point for incremental improvements. A complete rewrite requires an explicitly approved migration ticket.

### Product commitments

- Non-technical users can create projects, describe work packages, provide feedback, and understand the results.
- Development teams can centrally configure agents, models, checks, and MCP servers.
- Security-sensitive actions are visible, subject to limits, and recorded in auditable logs.
- Users retain control of their local data, credentials, and project source code.

## Target environment

Vibe runs in a Python environment on Linux, Windows, and macOS. Agents can optionally run in a sandbox to limit access to the host.

Diagnostics determine support for the actual operating system, containers, Python version, and optional tools. Missing optional components must not silently break core functionality.

## Terms and boundaries

- **Project source:** The source code in this Git repository.
- **Installation:** The deployed, executable application.
- **Runtime data:** Settings, logs, tokens, backups, and status records.
- **Global agent:** An agent available to all projects.
- **Project agent:** An agent available only within one project.
- **MCP server:** A service that provides tools through MCP.
- **Model profile:** A mapping of models to roles.
- **Agent run:** Execution of a work package through a harness supported by Vibe.
- **Dashboard:** The Vibe web application.
- **Runner:** The Vibe-managed process that coordinates work packages, Git workspaces, verification, and closing actions.

Source code, installation files, and runtime data are distinct. Updating one must not overwrite the others.

## Starting point and evidence

The initial application files are imported unchanged and recorded in a SHA-256 manifest.

Previous user confirmation establishes basic usability, not full conformity with this specification.

## Functional scope

### Projects and development directories

- List, add, remove, and rescan development directories.
- Recognize projects by Git metadata or Vibe project configuration.
- Distinguish projects with the same name in different directories.
- Removing a development directory from Vibe does not delete project files.
- Reject unsuitable, overly broad, or disallowed paths with a clear explanation.
- The project list shows name, type, branch, changes, open work packages, run status, and latest commit.
- The project detail view shows the path, feedback, tickets, logs, and available actions.
- Scanning a directory does not run builds, installations, or project commands.

### Project templates

- Provide templates for common project types, such as generic, Android, and web projects.
- Allow additional project types through templates.
- Support preparing existing projects without silently overwriting files.
- Report project creation and Git initialization errors clearly.
- Project types can provide their own verification adapters.

### Work packages and feedback

- Tickets, including work packages, bugs, and feedback, share a local, unversioned, machine-readable store: `.vibe/tickets.json`.
- Distinguish draft, open, in-progress, blocked, awaiting-merge, and completed tickets, including when GitHub is not connected.
- Users can add feedback and create, edit, or delete work packages through the UI.
- Assign IDs automatically unless the user supplies one. IDs must be unique, including during concurrent writes.
- Completion requires satisfied acceptance criteria and supporting evidence. A commit alone does not prove acceptance. A blocked ticket is not complete.
- Package handoff and closure are distinct. The runner validates evidence from the ticket working copy and updates the ticket store. An agent finishing its work does not mean the package has been integrated.
- In local mode, the runner merges an accepted package into the local integration branch and cleans up the package worktree and branch.
- In GitHub mode, the runner fetches the current integration state and merges it into the feature branch before pushing. Conflicts are resolved in the package worktree.
- Without auto-merge, the runner opens a PR and waits for manual merge and closure confirmation. The worktree remains registered in the meantime.
- With auto-merge enabled, the runner may squash-merge the approved PR after all gates pass. Final synchronization and cleanup follow confirmed merge.

### Agents

- List and filter global and project agents.
- Create, view, edit, copy, and delete agents.
- Edit the description, mode, model, permissions, and prompt through structured fields or raw text.
- Invalid input leaves the existing file unchanged.
- Make naming conflicts and agent shadowing visible.
- Preserve unknown fields wherever possible.
- Back up configurations before changes and support restoration.
- Product logic must not depend on hard-coded agent names. Assign coders and reviewers through configurable roles.

### Models and providers

- List models from available providers, not only `opencode/*`.
- Support model selection in the agent editor and both free and paid models.
- Credentials do not belong in agent files or this repository.
- Distinguish a listed model from one the user is authorized to use.
- A paid test request requires prior notice and consent.
- Do not invent model IDs or capabilities.

### Model table

- Provide an overview and assessment of available models.
- Include model ID, provider, availability, context size, image support, strengths, weaknesses, speed, effort, data terms, and price.
- Display unknown values explicitly.
- Distinguish facts, measurements, user reports, and assessments. Give the source, date, and test method where applicable.
- Prices specify currency, unit, input and output rates, and effective date. Show cache pricing, tiers, and surcharges separately.
- Mark stale information. Do not copy old assessments or prices without verification.

### Model profiles

- Create, edit, copy, delete, and apply profiles.
- Support configurable roles, including at least coder and reviewer, mapped to global or project agents.
- Preview the exact changes before applying a profile.
- Validate all target agents and models before the first write. Applying a profile must be transactional or fully reversible after partial failure.
- An empty profile must not report successful application.
- Show when later manual edits cause agents to differ from the profile.
- Clearly identify paid profiles. Never switch automatically from a free model to a paid model.

### MCP management

- List, create, edit, delete, enable, and disable global and project MCP servers.
- For local servers, manage the executable, argument list, and environment variables.
- For remote servers, manage the URL, headers, and supported authentication.
- Offer additional fields only when the installed version supports them.
- Document the actual configuration files and their precedence.
- Preserve unknown settings and comments where possible. If an edit cannot preserve a file faithfully, stop or request approval for a concrete change preview. Never silently discard data.
- Mask secrets and preserve their values when saving. Do not expose them in responses, errors, command displays, or logs.

### MCP connection checks

- Explain before a check that it may start programs or open network connections. A connectivity check is not guaranteed to be side-effect free.
- Check `initialize` and `tools/list`; display server identity and available tools. Do not automatically invoke functional tools.
- Distinguish missing executables, timeouts, DNS/TLS errors, HTTP errors, authentication failures, protocol failures, and invalid configuration.
- Show supported transports explicitly. An unsupported transport does not mean the server is defective.
- Limit execution time, output, and resource use. Reliably stop test processes and their children.
- A successful connection check does not establish that an agent may use every listed tool. Agent-specific permissions must be visible or traceable.

### Agent runs and verification

- Start, observe, attach to, and selectively stop runs.
- Show project, agent, start time, session, and current work package.
- Support concurrent runs for different projects without collisions between identical or normalized names.
- Provide live logs and separate verification logs.
- Missing verification configuration is an error, not a successful check.
- Package verification and full verification of the integration state are separate runner gates. Checks are configured per project; agents cannot replace the configured gate commands during a run.
- Retry and iteration limits are configurable. An iteration limit is not a spending budget and must not be labeled as one.
- An external signal (`HUP`, `TERM`, or `INT`) must not end a run without a trace. Record the signal, a log entry, and the run registry state.
- On startup, mark orphaned `running` entries for the current project as externally terminated. Leave other projects, active sessions, and sessions whose state cannot be determined unchanged. Never terminate another project's session.
- By default, quota and login failures stop a run immediately. The explicit global setting `vibe limits stop|continue`, stored in `<state>/limits.json`, applies to all projects.
- With `continue`, handle the failure within the existing retry limits and log a notice. A missing or invalid setting means `stop` and must be reported. Quota and login failures never trigger a router reconnection or manual IP lookup.

### Closing the application

- Closing a browser tab does not stop Vibe or any agent run. Reopening the dashboard shows the sessions that are still running.
- Explicitly quitting from the dashboard stops Vibe and its managed agent runs. Stopping the harness is a separate action.
- Stop only processes that can be identified as Vibe-managed.
- Explain the effects of each action in the UI. Tests must check that unrelated processes are not stopped.

### Start menu

- Install and remove a per-user menu entry.
- If Vibe is not running, start the required containers and Vibe, wait for readiness, and open the default browser.
- If Vibe is already running, open only the web interface. Repeated clicks must not start duplicate dashboard processes.
- Identify Vibe through its dedicated health endpoint. An unrelated application on the same port is not a running Vibe instance.
- Do not log the token. Support paths containing spaces and special characters.
- Normal operation must not require a visible terminal. Explain failures and provide a sanitized log.
- Honor custom paths, ports, and container settings consistently.
- The start-menu stop action affects only Vibe.

### Diagnostics

- Distinguish application prerequisites from optional project tools.
- Do not infer an entire configuration schema from an assumed major version.
- Detect host/container mismatches.
- Check writability, port availability, and required programs.
- Provide concrete, copyable remediation steps.

## Security and data integrity

- The web server binds to loopback by default. An explicitly configured network bind address must be an IP literal; reject DNS hostnames to prevent DNS rebinding.
- An IP/CIDR allowlist may restrict clients. Loopback remains allowed by that list.
- Authentication uses a token or password with a session cookie rather than leaving a permanent token in the browser.
- Mutating API requests require valid authentication. Enforce Host and Origin checks and CSRF protection.
- Never include tokens in access logs or error messages.
- Limit input and request sizes. Prevent path traversal and unauthorized symlink targets.
- Invoke external commands using argument lists rather than shell concatenation unless explicitly configured shell execution is required.
- Treat project check commands and MCP programs as trusted-code execution, not passive configuration.
- Write files atomically and detect concurrent changes.
- Backups must not collide and may contain sensitive data.
- Store sensitive runtime data on a suitably protected filesystem. Do not claim Unix permissions are effective on FUSE or NTFS without evidence.
- Never automatically add API keys, tokens, global configurations, or personal agents to Git.

## Architecture goals

Decouple the application incrementally:

- Keep the CLI and web API thin.
- Share domain services for projects, agents, profiles, and MCP.
- Put file access behind testable repository and storage functions.
- Return structured results from business logic rather than capturing stdout.
- Keep static frontend files separate from Python code.
- Importing modules must not start servers, containers, or programs.

Target layout, not a prerequisite for the initial unchanged import:

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

## Configuration and migration

- `$VIBE` identifies the workspace, not the source repository.
- Preserve existing `_toolchain` and `_logs` data during adoption. Never replace personal configuration with shipped defaults.
- Provide a preview and backup before migration.
- Support installation from the repository without manually copying individual files.
- Updates and rollbacks must preserve personal settings.
- Uninstallation must not remove projects or, by default, user data.
- Test changes to Vibe separately before updating the running installation. Do not overwrite the production instance during an agent run.

## Quality and acceptance

- Use unit tests for domain logic and validation, integration tests for API, storage, and process adapters, and browser tests for core workflows.
- Mocks alone do not replace browser or system acceptance checks.
- Tests use temporary directories and dedicated ports, not personal projects or production configuration.
- Verification records state the command, result, and limits of the evidence.
- Every ticket requires functional and technical evidence and an independent review. Changed testable behavior must be demonstrated by suitable tests. Existing tests are sufficient if they were run and demonstrate the criterion. For changes without meaningful runtime behavior, document an appropriate alternative check.

## Out of scope

- Hosting models or operating a payment service.
- Public remote access to the dashboard.
- Multi-user operation or cloud synchronization.
- Automatic publication, push, merge, or release without authorization. Automatic GitHub merge requires the configured opt-in.
- A complete framework change as a prerequisite for continued development.

## Locked decisions

- Import the existing source; do not regenerate it.
- Do not mark functionality complete before it has been verified.
- Retain the local web application and CLI.
- Decouple features incrementally.
- Keep runtime data and secrets out of the repository.
- Mark unverified model information as unknown.
- Address security and data-integrity defects before convenience features.

## Audience and use

Vibe is intended for consultants, product owners, project managers, and others who want to build reliable software without needing deep development expertise.

Users describe goals, requirements, and feedback. Technical configuration, agent runs, and verification remain visible and controllable while Vibe coordinates the development workflow.
