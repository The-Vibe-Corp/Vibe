# Installation, update, and release

Status: current as of 2026-11-25 (vibe 0.18.0, repository state). Authority: [SPEC.md](../../../SPEC.md).
History: see the ticket records linked at the end.

Installation changes program files only. Runtime data, personal configuration,
backups, and projects survive updates and uninstalls; source, installation, and
runtime remain separate paths (`V-006`).

## Setup

- `install-vibe.sh` requires `VIBE` and delegates to
  `scripts/setup-vibe.py --yes --update --vibe "$VIBE" --source "$KIT"`.
  `setup-vibe.cmd` is the Windows entry point.
- The setup detects Linux distribution, container, or Windows, checks required
  tools, offers installation through the present package manager, and writes
  the program files. It does not run project commands, model calls, or router
  actions.
- Modes include install/reuse, `--update`, `--rollback`, and `--uninstall`;
  `--preview` (alias `--dry-run`) prints the plan without writing, and
  `--version` prints the source version.
- An update makes a backup (`backup-<timestamp>/` with `backup.json`).
  `--rollback` restores a chosen or the newest backup. Uninstall removes the
  installed program files; projects and runtime data remain.

## Protection of the running instance

- `--update` on the active installation is refused unless an authorized
  `--source` is supplied. Updates, rollbacks, and uninstalls are also refused
  while an agent run, dashboard, or opencode session is active; `--force`
  overrides this deliberately.
- The installed `version.json` records version, commit, and source of the
  release; `VERSION` is used when the repository is the source. The dashboard
  exposes the same release identity through `/api/health` and `vibe doctor`.

## Integrity and release evidence

- `docs/import-manifest.json` lists SHA-256 hashes for the imported program
  files and metadata. `scripts/check-import-manifest.py` verifies them as part
  of `quick`; the current manifest covers 70 files.
- `docs/baseline-installation.sha256` is the snapshot of the active
  installation produced with `scripts/active-install.py snapshot`. Its `verify`
  mode checks that the installation still matches; runtime data and caches are
  outside the scope.
- `scripts/build-release.py` builds a release from versioned files without
  personal data.

## Bazzite starter and desktop entry

- `scripts/vibe_starter.py start|stop|status` enters the container if needed,
  starts the dashboard, waits for `/api/health`, and opens the browser. A file
  lock prevents duplicate dashboards, and a foreign service on the port is not
  adopted as Vibe.
- `scripts/vibe-desktop.py install|uninstall|status` installs or removes the
  per-user menu entry, starter, and icon. Uninstall removes only files whose
  checksum still matches its install manifest.

## Discrepancy note

`V-001.md` says the import manifest had 22 entries; the current manifest has
71 because later tickets added files.

## Entry points

- CLI: `./install-vibe.sh`, `setup-vibe.cmd`,
  `python3 scripts/setup-vibe.py`, `python3 scripts/vibe_starter.py`,
  `python3 scripts/vibe-desktop.py`, `python3 scripts/active-install.py`.
- Files: `VERSION`, `<install>/version.json`, `<install>/backup-*/backup.json`,
  `docs/import-manifest.json`, `docs/baseline-installation.sha256`.

## Records

- [B4-install-leerer-laufzustand](../B4-install-leerer-laufzustand.md) — install with empty run state
- [F6](../F6.md) — universal setup process
- [REPO-CLEANUP-GITHUB](../REPO-CLEANUP-GITHUB.md) — repository cleanup for publication
- [V-006](../V-006.md) — separate source, installation, and runtime paths
- [V-017](../V-017.md) — production-ready Bazzite starter
- [V-018](../V-018.md) — install, update, and rollback
- [V-020](../V-020.md) — browser acceptance, documentation, release base
- [V-021](../V-021.md) — install completeness and cleanup rules
