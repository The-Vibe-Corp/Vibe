# Installation

Vibe ist eine lokal betriebene Entwicklungszentrale für KI-assistierte Softwareprojekte. Die Installation trennt Quellcode, installierte Anwendung und Laufzeitdaten voneinander. [cite:1]

## Voraussetzungen

- Python-Umgebung
- Linux, Windows oder macOS
- Optional: Docker, Podman, Toolbx oder Distrobox
- Optional: Git

Vibe ermittelt die tatsächliche Unterstützung über Diagnostics. Dabei werden Betriebssystem, Container, Python-Version und optionale Werkzeuge geprüft. Fehlende optionale Komponenten dürfen die Kernfunktionalität nicht still beschädigen. [cite:1]

## Workspace festlegen

`$VIBE` bezeichnet den **Workspace**, nicht das Vibe-Quellcode-Repository. Dort liegen die von Vibe verwalteten Laufzeitdaten, Einstellungen, Logs, Backups und Statusinformationen. [cite:1]

Beispiel:

```bash
export VIBE="$HOME/vibe-workspace"
```

## Linux installieren

Der Repository-Installer ist `install-vibe.sh`. Er ist ein kompatibler Einstiegspunkt für Linux und ruft das plattformübergreifende Setup `scripts/setup-vibe.py` auf. [cite:2]

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe

VIBE="$HOME/vibe-workspace" bash install-vibe.sh
```

Der Aufruf installiert bzw. aktualisiert Vibe ohne Rückfragen. Das Setup verwendet das geklonte Repository als Quelle und den angegebenen `VIBE`-Pfad als Workspace. [cite:2]

## Windows installieren

Für Windows existiert `setup-vibe.cmd` als eigener Einstiegspunkt. [cite:0]

```powershell
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
.\setup-vibe.cmd
```

## Container-Umgebungen

Vibe unterstützt den Betrieb in Container-Umgebungen. Diagnostics erkennen Host-/Container-Mismatch, prüfen Schreibrechte, Portverfügbarkeit und erforderliche Programme sowie liefern konkrete, kopierbare Remediation-Schritte. [cite:1]

## Update und Rollback

Updates und Rollbacks müssen persönliche Einstellungen erhalten. Eine Deinstallation entfernt standardmäßig weder Projekte noch Nutzerdaten. [cite:1]

Wichtige Regeln:

- Ändere Vibe zunächst separat, bevor du die laufende Installation aktualisierst.
- Überschreibe während eines Agent Runs nicht die Produktionsinstanz.
- Erhalte bestehende `_toolchain`- und `_logs`-Daten bei der Adoption.
- Ersetze persönliche Konfiguration nicht durch ausgelieferte Defaults. [cite:1]

## Nach der Installation

1. Starte das lokale Dashboard.
2. Füge ein Entwicklungverzeichnis hinzu.
3. Prüfe Diagnostics.
4. Konfiguriere bei Bedarf Agenten, Modelle und MCP-Server.
5. Lege dein erstes Work Package an.

Das Entfernen eines Entwicklungverzeichnisses aus Vibe löscht keine Projektdateien. Das Scannen eines Verzeichnisses führt ebenfalls keine Builds, Installationen oder Projekt-Commands aus. [cite:1]
