# Projects and development directories

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

Vibe lists projects from a set of development roots. A project is identified
by Git metadata or a `.vibe` configuration. Scanning only reads directory
metadata; it never runs builds, installations, or project commands.

## Development roots

- The roots are the configured Vibe workspace plus extra paths stored under
  `roots` in `<state>/vibe.json`.
- `vibe roots add <path>` and `vibe roots rm <path>` change the extras. Paths
  are compared by `realpath`, so the same directory is not added twice.
- Broad or system locations are rejected with a clear message (`BAD_ROOTS`:
  `/`, `/usr`, `/etc`, `/tmp`, `/home`, `/var`), as is the user's home
  directory. Removing a root never deletes project files.

## Discovery

- A scan looks at immediate subdirectories only and accepts a directory when it
  contains `.git` or `.vibe`.
- Symlink aliases collapse by resolved path, so one project appears once.
- Duplicate project names remain distinct under a `name@root` key; the UI shows
  that qualified name.
- The list shows name, type, branch, changes, open packages, run status, and
  the latest commit.

## Type resolution

`TYPE` in `<project>/.vibe/project.env` wins. Otherwise markers decide:
`gradlew` → android, `pubspec.yaml` → flutter, `package.json` → web,
`pyproject.toml` → python, `docker-compose.yml`/`compose.yaml` → docker; else generic.

## Preparing, creating, cloning

- `vibe init <name> [type]` copies `templates/common` and `templates/<type>`
  into an existing directory without overwriting files, ensures `.gitignore`
  excludes `.vibe/`, and does not commit.
- `vibe new` creates the directory under the Vibe workspace and runs
  `git init` plus an initial commit.
- `vibe clone <url> [name] [--branch <branch>]` checks out a repository, adds
  missing template files, keeps non-managed environment keys, remaps project
  agents to local agents, and stores github.com repositories as
  `GITHUB_ENABLED=1` with `GITHUB_REPO=<owner/name>`. It does not commit the
  adopted changes.

## Project assistant and detail view

The assistant (`bin/vibe_guide.py`) walks through eight questions and writes
`SPEC.md`. It creates a missing `AGENTS.md`, `.vibe/project.env`, and
`README.md` without overwriting existing content. Drafts are only applied on
an explicit action.

The project detail view has five tabs: overview, work, output, assistant
(labelled "Beschreibung"), and settings (`bin/web/nova-project.js`).

## Discrepancy note

F9.md's file list and F13.md's four tabs are historical; the current detail
view has five tabs.

## Entry points

- CLI: `vibe roots`, `vibe types`, `vibe init`, `vibe new`, `vibe clone`.
- HTTP: `/api/roots`, `/api/init`, `/api/new`, `/api/types`, `/api/clone`,
  `/api/guide` (project assistant).
- Files: `<state>/vibe.json`, `<project>/.vibe/project.env`,
  `templates/<type>/`.

## Records

- [F2](../F2.md) — project detail and editable feedback
- [F9](../F9.md) — project assistant for the functional setup
- [F13](../F13.md) — restructured project detail
- [F14](../F14.md) — project type "Rebuild"
- [AP15](../AP15.md) — fast project view opening
- [V-008](../V-008.md) — project management and template regression checks
