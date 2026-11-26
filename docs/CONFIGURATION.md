# Configuration

Vibe separates project source code, installation, and runtime data. Settings, logs, tokens, backups, and status records are runtime data and are not managed in the source repository.

## Workspace

`$VIBE` identifies the Vibe workspace. It is the central location for Vibe-managed runtime data.

```bash
export VIBE="$HOME/vibe-workspace"
```

## Data model

| Layer | Contents | Handling |
|---|---|---|
| **Project source** | Source code in a Git repository | Remains in the respective project |
| **Installation** | Deployed, executable Vibe application | Managed through installation and updates |
| **Runtime data** | Settings, logs, tokens, backups, status | Remains local in the workspace |

This separation is binding: updating one layer must not overwrite the others.

## Projects

Vibe can manage development directories and recognize projects through Git metadata or Vibe project configuration. Projects with the same name in different directories are distinguished.

- Add, remove, and rescan development directories.
- Show project name, type, branch, changes, open work packages, run status, and latest commit.
- Show project path, feedback, tickets, logs, and available actions in the project detail view.
- Reject unsuitable, overly broad, or disallowed paths with a clear explanation.

## Project templates

Vibe provides templates for common project types, including generic, Android, and web projects. Additional project types can be added through templates.

Templates prepare existing projects without silently overwriting files. Project creation and Git initialization errors are reported clearly. Project types can provide their own verification adapters.

## Tickets and work packages

Tickets, including work packages, bugs, and feedback, are stored in a local, unversioned, machine-readable store: `.vibe/tickets.json`.

Supported statuses:

- `draft`
- `open`
- `in-progress`
- `blocked`
- `awaiting-merge`
- `completed`

IDs are assigned automatically unless the user provides one. They must remain unique, including during concurrent writes.

## Migration

When adopting existing installations, `_toolchain` and `_logs` data must be preserved. Personal configuration must not be replaced with shipped defaults.

A preview and backup are provided before migration. Updates and rollbacks preserve personal settings; uninstallation does not remove projects or, by default, user data.
