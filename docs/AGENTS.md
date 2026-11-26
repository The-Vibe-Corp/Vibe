# Agents

Vibe manages global and project-specific AI agents. A **global agent** is available to all projects, while a **project agent** is available only within a single project.

## Managing agents

In the dashboard, you can:

- List and filter agents
- Create agents
- View agents
- Edit agents
- Copy agents
- Delete agents

Editing covers description, mode, model, permissions, and prompt, either through structured fields or raw text.

## Configuration rules

- Invalid input leaves the existing agent file unchanged.
- Naming conflicts and agent shadowing are made visible.
- Unknown fields are preserved wherever possible.
- Configurations are backed up before changes, and restoration is supported.

## Roles instead of fixed names

Vibe logic must not depend on hard-coded agent names. Coders and reviewers are assigned through configurable roles.

| Role | Typical purpose |
|---|---|
| **Coder** | Implements a work package |
| **Reviewer** | Reviews the result, evidence, and technical quality |

## Assigning models

Agents can use models from available providers. Vibe distinguishes between a listed model and a model the user is actually authorized to use.

- Credentials do not belong in agent files or this repository.
- Paid test requests require prior notice and consent.
- Model IDs and capabilities are not invented.

See [docs/MODELS.md](docs/MODELS.md) for model and model-profile details.

## Agent runs

An **agent run** is the execution of a work package through a harness supported by Vibe. Vibe is not itself an AI harness; it works with external, interchangeable harnesses through isolated execution and configuration interfaces. OpenCode is a supported harness.

Agent runs can be started, observed, attached to, and selectively stopped. The dashboard shows the project, agent, start time, session, and current work package.

## Concurrent runs

Vibe supports concurrent runs for different projects without collisions between identical or normalized names. Live logs and separate verification logs are available.

## Stopping and completion

- Closing a browser tab does not stop Vibe or an agent run.
- Reopening the dashboard shows sessions that are still running.
- Explicitly quitting from the dashboard stops Vibe and its managed agent runs.
- Stopping the harness is a separate action.

Vibe stops only processes that can be identified as Vibe-managed.
