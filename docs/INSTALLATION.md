# Installation

Vibe is a locally operated development hub for AI-assisted software projects. Installation separates project source code, the installed application, and runtime data. [cite:1]

## Prerequisites

- A Python environment
- Linux, Windows, or macOS
- Optional: Docker, Podman, Toolbx, or Distrobox
- Optional: Git

Vibe determines actual support through diagnostics. It checks the operating system, containers, Python version, and optional tools. Missing optional components must not silently break core functionality. [cite:1]

## Set the workspace

`$VIBE` identifies the **workspace**, not the Vibe source repository. It is where Vibe stores managed runtime data, settings, logs, backups, and status records. [cite:1]

Example:

```bash
export VIBE="$HOME/vibe-workspace"
```

## Install on Linux

The repository installer is `install-vibe.sh`. It is a compatible Linux entry point and invokes the cross-platform setup script, `scripts/setup-vibe.py`. [cite:2]

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe

VIBE="$HOME/vibe-workspace" bash install-vibe.sh
```

This command installs or updates Vibe without prompts. The setup uses the cloned repository as its source and the specified `VIBE` path as its workspace. [cite:2]

## Install on Windows

Vibe provides `setup-vibe.cmd` as the Windows entry point. [cite:0]

```powershell
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
.\setup-vibe.cmd
```

## Container environments

Vibe supports operation in container environments. Diagnostics detect host/container mismatches, check write permissions, port availability, and required programs, and provide concrete, copyable remediation steps. [cite:1]

## Updates and rollback

Updates and rollbacks must preserve personal settings. Uninstallation must not remove projects or, by default, user data. [cite:1]

Important rules:

- Test changes to Vibe separately before updating the running installation.
- Do not overwrite the production instance during an agent run.
- Preserve existing `_toolchain` and `_logs` data during adoption.
- Do not replace personal configuration with shipped defaults. [cite:1]

## After installation

1. Start the local dashboard.
2. Add a development directory.
3. Review diagnostics.
4. Configure agents, models, and MCP servers as needed.
5. Create your first work package.

Removing a development directory from Vibe does not delete project files. Scanning a directory also does not run builds, installations, or project commands. [cite:1]
