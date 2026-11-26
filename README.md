<div align="center">

# Vibe

**Die lokale Entwicklungszentrale für deine Vibe-Coding-Projekte.**

Verwalte Projekte, KI-Agenten, Modelle und MCP-Server an einem Ort — lokal, schnell und ohne dich zwischen Tools und Terminals zu verlieren.

[![GitHub release](https://img.shields.io/github/v/release/The-Vibe-Corp/Vibe?style=flat-square)](https://github.com/The-Vibe-Corp/Vibe/releases)
[![License](https://img.shields.io/github/license/The-Vibe-Corp/Vibe?style=flat-square)](./LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue?style=flat-square)](#installation)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](./CONTRIBUTING.md)

[Features](#features) ·
[Schnellstart](#schnellstart) ·
[Installation](#installation) ·
[Dokumentation](#dokumentation) ·
[Beitragen](#beitragen)

</div>

---

## Warum Vibe?

Vibe-Coding bedeutet, mit KI-Agenten schnell Ideen in funktionierende Software zu übersetzen. Dabei entstehen jedoch schnell viele parallele Projekte, unterschiedliche Modelle, Agenten-Konfigurationen und MCP-Server.

**Vibe bringt Struktur in dieses Chaos.**

Es ist eine lokale Steuerzentrale, mit der du Projekte und deren KI-Umgebung übersichtlich organisierst — ohne deine Arbeit aus der Kommandozeile oder deinem Editor herauszureißen.

## Features

- **Projektzentrale** — Verwalte mehrere Vibe-Coding-Projekte zentral an einem Ort.
- **Agenten-Verwaltung** — Konfiguriere und organisiere KI-Agenten pro Projekt.
- **Modell-Katalog** — Verwalte verfügbare Modelle und deren Einstellungen.
- **MCP-Server-Integration** — Verbinde und verwalte Model Context Protocol Server für deine Agenten.
- **Profile** — Erstelle wiederverwendbare Konfigurationsprofile für unterschiedliche Arbeitsweisen.
- **Lokal first** — Deine Projekte, Konfigurationen und Laufzeitdaten bleiben auf deinem Rechner.
- **Plattformübergreifend** — Unterstützung für Linux-Distributionen, Container-Umgebungen und Windows.

## Architektur

Vibe organisiert deine lokale Entwicklungsumgebung um vier zentrale Bausteine:

| Baustein | Zweck |
|---|---|
| **Projects** | Zentrale Verwaltung deiner Vibe-Coding-Projekte |
| **Agents** | Konfiguration und Verwaltung deiner KI-Agenten |
| **Models** | Übersicht und Verwaltung verfügbarer Modelle |
| **MCP Servers** | Anbindung und Verwaltung von MCP-Servern |

Projektspezifische Daten werden lokal im jeweiligen `.vibe`-Verzeichnis abgelegt. Globale Laufzeitdaten wie `vibe.json`, `models.json`, `profiles.json` und `fritz.json` werden zentral verwaltet.

## Schnellstart

### Voraussetzungen

- Linux, Windows oder eine Container-Umgebung wie Docker, Podman, Toolbx oder Distrobox
- Git
- <!-- TODO: Weitere konkrete Voraussetzungen ergänzen, z. B. Node.js, Python, Go oder eine bestimmte CLI -->

### Installation

```bash
curl -fsSL https://raw.githubusercontent.com/The-Vibe-Corp/Vibe/dev/install-vibe.sh | bash
```

Der Installer erkennt automatisch deine Umgebung — einschließlich Ubuntu/Debian, Fedora, Bazzite, Docker, Podman, Toolbx, Distrobox und Windows. Fehlende Werkzeuge werden nur nach deiner Zustimmung installiert. Eine bereits vorhandene Vibe-Installation wird standardmäßig wiederverwendet.

### Vibe aktualisieren

```bash
vibe --update
```

Das ersetzt die Programmdateien und erstellt dabei ein Backup der bisherigen Installation.

### Erstes Projekt starten

```bash
# TODO: Tatsächlichen CLI-Befehl ergänzen
vibe init
```

Danach öffnest du Vibe und legst dein erstes Projekt, einen Agenten sowie optional einen MCP-Server an.

<!-- TODO: Optional Screenshot oder GIF einfügen -->

![Vibe Overview](docs/assets/overview.png)

## Installation

### Linux

Der empfohlene Weg ist das Installationsskript:

```bash
curl -fsSL https://raw.githubusercontent.com/The-Vibe-Corp/Vibe/dev/install-vibe.sh | bash
```

Unterstützte Umgebungen:

- Ubuntu und Debian
- Fedora
- Bazzite
- Docker
- Podman
- Toolbx
- Distrobox

### Windows

<!-- TODO: Windows-Installationsanleitung ergänzen, z. B. PowerShell-Befehl oder Download-Link -->

```powershell
# TODO: Windows-Installer oder PowerShell-Befehl
```

### Manuelle Installation

<!-- TODO: Manuelle Installation ergänzen, falls unterstützt -->

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
# TODO: Build- und Installationsbefehle ergänzen
```

## Konfiguration

Vibe speichert seine Konfiguration lokal und trennt globale Einstellungen von projektspezifischen Daten.

| Datei / Verzeichnis | Zweck |
|---|---|
| `vibe.json` | Zentrale Laufzeit- und Anwendungskonfiguration |
| `models.json` | Verfügbare Modelle und deren Konfiguration |
| `profiles.json` | Wiederverwendbare Arbeits- und Agentenprofile |
| `fritz.json` | Projektspezifische bzw. integrationsbezogene Konfiguration |
| `.vibe/` | Lokale, projektspezifische Vibe-Daten |
| Log-Verzeichnis | Diagnose- und Laufzeitprotokolle |

## Dokumentation

- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Agenten einrichten](#agenten-einrichten)
- [MCP-Server verbinden](#mcp-server-verbinden)
- [Beitragen](#beitragen)

<!-- TODO: Links zu docs/, wiki oder Website ergänzen -->

## Projektstruktur

```text
Vibe/
├── .github/              # CI, Templates und Repository-Konfiguration
├── install-vibe.sh       # Plattformübergreifender Installer
├── README.md
├── LICENSE
└── # TODO: Tatsächliche Quellcode-Struktur ergänzen
```

## Entwicklung

### Repository klonen

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
```

### Abhängigkeiten installieren

```bash
# TODO: Installationsbefehl ergänzen
```

### Entwicklung starten

```bash
# TODO: Dev-Server bzw. lokalen Start ergänzen
```

### Tests ausführen

```bash
# TODO: Testbefehl ergänzen
```

## Beitragen

Beiträge sind willkommen — ob Bugfix, neue Integration, Dokumentation oder Verbesserung der Developer Experience.

1. Forke das Repository
2. Erstelle einen Feature-Branch: `git checkout -b feature/mein-feature`
3. Nimm deine Änderungen vor
4. Teste sie lokal
5. Erstelle einen Pull Request

Bitte halte Pull Requests fokussiert und beschreibe klar, welches Problem sie lösen.

## Support

- **Bugs und Feature-Wünsche:** [GitHub Issues](https://github.com/The-Vibe-Corp/Vibe/issues)
- **Diskussionen:** <!-- TODO: GitHub Discussions oder Community-Link ergänzen -->
- **Sicherheitsmeldungen:** Bitte keine Sicherheitsprobleme öffentlich in Issues melden. Kontaktiere das Maintainer-Team direkt.

## Lizenz

<!-- TODO: Lizenz ergänzen, z. B. MIT, Apache-2.0 oder AGPL-3.0 -->

```text
TODO: LICENSE einfügen
```

---

<div align="center">

**Vibe** — Projektmangement für dein Vibe Coding.

</div>
