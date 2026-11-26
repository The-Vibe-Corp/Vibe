<div align="center">

# Vibe

**Die lokale Entwicklungszentrale für KI-gestützte Softwareprojekte.**

Vibe verbindet Projekte, Agenten, Modelle, MCP-Server, Ausführungen, Verifikation und Diagnose in einer lokal betriebenen Web-Oberfläche und CLI.

[![License](https://img.shields.io/github/license/The-Vibe-Corp/Vibe?style=flat-square)](./LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-blue?style=flat-square)](docs/INSTALLATION.md)
[![Contributing](https://img.shields.io/badge/contributions-welcome-brightgreen?style=flat-square)](./CONTRIBUTING.md)
[![Security](https://img.shields.io/badge/security-policy-available-informational?style=flat-square)](./SECURITY.md)

[Features](#features) ·
[Schnellstart](#schnellstart) ·
[Dokumentation](#dokumentation) ·
[Architektur](#architektur) ·
[Beitragen](#beitragen)

</div>

---

## Was ist Vibe?

Vibe ist ein **lokaler Development Hub** für KI-assistierte Softwareprojekte. Statt Agenten, Modelle, MCP-Server, Tickets, Logs und Verifikation über viele getrennte Werkzeuge zu verwalten, bündelt Vibe diese Bausteine in einer übersichtlichen Arbeitsumgebung.

Vibe ist dabei **kein AI Harness**: Es arbeitet mit austauschbaren, externen Harnesses über isolierte Ausführungs- und Konfigurationsschnittstellen. OpenCode ist ein unterstützter Harness. [cite:1]

Die Anwendung richtet sich insbesondere an Consultants, Product Owner, Project Manager und alle, die zuverlässige Software entwickeln möchten, ohne selbst tief in der Entwicklungstechnik zu stecken. Nutzer beschreiben Ziele, Anforderungen und Feedback; technische Konfiguration, Agent-Runs und Verifikation bleiben sichtbar und kontrollierbar. [cite:1]

## Features

| Bereich | Was Vibe bietet |
|---|---|
| **Projekte** | Entwicklungverzeichnisse verwalten, Projekte über Git-Metadaten oder Vibe-Konfiguration erkennen, Status, Branch, Änderungen, offene Tickets und letzten Commit anzeigen. |
| **Work Packages** | Tickets, Bugs, Feedback und Arbeitspakete lokal verwalten — inklusive Status, Akzeptanzkriterien, Nachweisen und Integration. |
| **Agenten** | Globale und projektspezifische Agenten erstellen, bearbeiten, kopieren, löschen und über Rollen zuweisen. |
| **Modelle** | Modelle verschiedener Provider verwalten, bewerten und in Modellprofilen rollenbasiert zuordnen. |
| **MCP-Server** | Lokale und remote MCP-Server verwalten, Verbindungen prüfen und verfügbare Tools anzeigen. |
| **Agent Runs** | Läufe starten, beobachten, Logs einsehen, gezielt stoppen und mehrere Projekte parallel betreiben. |
| **Verifikation** | Paket- und Integrationsverifikation als separate Gates konfigurieren und Nachweise dokumentieren. |
| **Diagnose** | Betriebssystem, Container, Python-Version, Ports, Schreibrechte und optionale Tools prüfen. |
| **Lokal first** | Quellcode, Installation und Laufzeitdaten bleiben getrennt; Nutzer behalten Kontrolle über lokale Daten, Zugangsdaten und Projektquellen. |

Diese Funktionalitäten folgen der verbindlichen Produktspezifikation in [`SPEC.md`](./SPEC.md). [cite:1]

## Schnellstart

### Voraussetzungen

- Python-Umgebung
- Linux, Windows oder macOS
- Optional: Docker, Podman, Toolbx oder Distrobox für containerisierte Umgebungen
- Optional: Git für projektbezogene Workflows

Vibe erkennt die tatsächliche Umgebung über Diagnostics und unterscheidet dabei zwischen zwingenden Anwendungsvoraussetzungen und optionalen Projektwerkzeugen. Fehlende optionale Komponenten dürfen die Kernfunktion nicht still beschädigen. [cite:1]

### Installation unter Linux

Der Linux-Einstiegspunkt ist `install-vibe.sh`. Er setzt voraus, dass die Umgebungsvariable `VIBE` auf deinen Vibe-Workspace zeigt, und ruft das plattformübergreifende Setup `scripts/setup-vibe.py` auf. [cite:2]

```bash
VIBE=/pfad/zu/deinem/vibe-workspace bash install-vibe.sh
```

Das Skript installiert bzw. aktualisiert Vibe ohne Rückfragen und verwendet das aktuelle Repository als Quelle. [cite:2]

### Installation unter Windows

Für Windows befindet sich ein eigener Einstiegspunkt im Repository:

```powershell
.\setup-vibe.cmd
```

Details zu Pfaden, Workspace, Containern und Update-Verhalten findest du in [docs/INSTALLATION.md](docs/INSTALLATION.md).

### Dashboard öffnen

Nach dem Start öffnest du das lokale Vibe-Dashboard im Browser. Vibe bindet den Webserver standardmäßig an `loopback`; ein explizit konfigurierter Netzwerk-Bind muss eine IP-Adresse sein, kein DNS-Hostname. [cite:1]

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [Installation](docs/INSTALLATION.md) | Installation, Update, Workspace, Windows, Linux und Container |
| [Konfiguration](docs/CONFIGURATION.md) | Workspace, Laufzeitdaten, Projekte, Profile und Migration |
| [Agenten](docs/AGENTS.md) | Globale und projektbezogene Agenten, Rollen, Berechtigungen und Prompts |
| [Modelle](docs/MODELS.md) | Provider, Modellprofile, Kosten, Verfügbarkeit und Bewertungsgrundsätze |
| [MCP-Server](docs/MCP.md) | Lokale und remote MCP-Server, Verbindungstests, Transporte und Sicherheit |
| [Workflows](docs/WORKFLOWS.md) | Tickets, Work Packages, Agent Runs, Verifikation und Integration |
| [Entwicklung](docs/DEVELOPMENT.md) | Repository-Struktur, Tests, Qualitätskriterien und Contributions |
| [Sicherheit](docs/SECURITY.md) | Lokale Datenhoheit, Authentifizierung, Secrets, Sandbox und Auditing |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Diagnose, häufige Fehler, Logs und sichere Fehlerbehebung |

## Architektur

Vibe trennt bewusst **Quellcode**, **Installation** und **Laufzeitdaten**. Ein Update einer dieser Ebenen darf die anderen nicht überschreiben. [cite:1]

```text
Projektquellen  ──►  Vibe Workspace  ──►  Agent Runs  ──►  Verifikation  ──►  Integration
       │                  │                  │                 │                  │
       └── Git / Dateien  └── Konfiguration   └── Harness       └── Nachweise      └── Merge / PR
```

Zentrale Begriffe:

| Begriff | Bedeutung |
|---|---|
| **Project source** | Quellcode im Git-Repository |
| **Installation** | Die deployed, ausführbare Vibe-Anwendung |
| **Runtime data** | Einstellungen, Logs, Tokens, Backups und Statusdaten |
| **Global agent** | Ein für alle Projekte verfügbarer Agent |
| **Project agent** | Ein Agent, der nur innerhalb eines Projekts verfügbar ist |
| **MCP server** | Ein Dienst, der Tools über MCP bereitstellt |
| **Model profile** | Eine Zuordnung von Modellen zu Rollen |
| **Agent run** | Die Ausführung eines Work Packages über einen unterstützten Harness |
| **Dashboard** | Die Vibe-Webanwendung |
| **Runner** | Der von Vibe verwaltete Prozess für Work Packages, Git-Workspaces, Verifikation und Abschlussaktionen |

Die Definitionen stammen aus der Produktspezifikation. [cite:1]

## Workflows

Vibe koordiniert den Weg von einer Idee bis zur integrierten Änderung:

1. **Projekt registrieren** — Entwicklungverzeichnis hinzufügen oder vorhandenes Projekt erkennen.
2. **Anforderung erfassen** — Feedback, Bug oder Work Package anlegen.
3. **Agent auswählen** — Geeigneten Coder- und Reviewer-Agenten über Rollen zuweisen.
4. **Ausführung starten** — Den Agent Run über einen unterstützten Harness starten.
5. **Ergebnis prüfen** — Live-Logs, Verifikationslogs und Nachweise einsehen.
6. **Integration abschließen** — Lokal mergen oder, sofern konfiguriert, einen GitHub-Pull-Request erstellen.

Ein Commit allein beweist keine Akzeptanz: Der Abschluss eines Work Packages erfordert erfüllte Akzeptanzkriterien und geeignete Nachweise. [cite:1]

## Sicherheit und Datenhoheit

Vibe ist lokal ausgerichtet. Der Webserver bindet sich standardmäßig an Loopback, authentifizierte mutating API-Anfragen sind erforderlich, und Tokens dürfen weder in Access-Logs noch in Fehlermeldungen erscheinen. [cite:1]

Wichtige Grundsätze:

- Nutzer behalten Kontrolle über lokale Daten, Zugangsdaten und Projektquellen.
- Sicherheitsrelevante Aktionen sind sichtbar, begrenzt und in auditierbaren Logs nachvollziehbar.
- Credentials gehören weder in Agent-Dateien noch in dieses Repository.
- Projekt-Check-Commands und MCP-Programme werden als trusted-code execution behandelt.
- Dateien werden atomar geschrieben; gleichzeitige Änderungen werden erkannt.
- API-Keys, Tokens, globale Konfigurationen oder persönliche Agenten werden niemals automatisch zu Git hinzugefügt.

Details findest du in [docs/SECURITY.md](docs/SECURITY.md) und [`SECURITY.md`](./SECURITY.md). [cite:1]

## Projektstruktur

```text
Vibe/
├── .github/               # GitHub-Konfiguration und Workflows
├── bin/                   # Ausführbare Einstiegspunkte
├── data/                  # Statische bzw. mitgelieferte Daten
├── docs/                  # Projekt- und Nutzerdokumentation
├── scripts/               # Setup, Wartung und Hilfsskripte
├── templates/             # Projekt- und Konfigurationsvorlagen
├── tests/                 # Unit-, Integrations- und Browser-Tests
├── install-vibe.sh        # Linux-Einstiegspunkt für Installation und Update
├── setup-vibe.cmd         # Windows-Einstiegspunkt
├── SPEC.md                # Verbindliche Produktspezifikation
├── CONTRIBUTING.md        # Beitragsrichtlinien
├── SECURITY.md            # Sicherheitsrichtlinie
├── CODE_OF_CONDUCT.md     # Verhaltenskodex
└── LICENSE                # Lizenz einschließlich kommerzieller Ausnahme
```

Die Struktur entspricht dem aktuellen Repository-Bestand. [cite:0]

## Entwicklung

```bash
git clone https://github.com/The-Vibe-Corp/Vibe.git
cd Vibe
```

Vibe verfolgt einen inkrementellen Decoupling-Ansatz: CLI und Web-API bleiben schlank, Domänenlogik wird in gemeinsame Services ausgelagert, Dateizugriff liegt hinter testbaren Storage-Funktionen und statische Frontend-Dateien sind vom Python-Code getrennt. [cite:1]

Qualität wird durch Unit-Tests für Domänenlogik, Integrations-Tests für API, Storage und Prozess-Adapter sowie Browser-Tests für zentrale Workflows gesichert. Mocks ersetzen dabei keine Browser- oder System-Akzeptanztests. [cite:1]

Details findest du in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) und [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Beitragen

Beiträge sind willkommen. Bitte halte Änderungen fokussiert, beschreibe das gelöste Problem klar und liefere geeignete funktionale sowie technische Nachweise.

1. Forke das Repository.
2. Erstelle einen Branch: `git checkout -b feature/mein-feature`.
3. Implementiere die Änderung inklusive passender Tests.
4. Führe relevante Tests und Verifikation aus.
5. Öffne einen Pull Request mit klarer Beschreibung und Nachweisen.

Die vollständigen Richtlinien findest du in [`CONTRIBUTING.md`](./CONTRIBUTING.md) und [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Support

- **Bugs und Feature-Wünsche:** [GitHub Issues](https://github.com/The-Vibe-Corp/Vibe/issues)
- **Sicherheitsmeldungen:** Siehe [`SECURITY.md`](./SECURITY.md)
- **Verhaltenskodex:** [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)

## Lizenz

Vibe steht unter der in [`LICENSE`](./LICENSE) enthaltenen Lizenz.

Die Lizenzdatei bleibt unverändert und enthält die bestehende Ausnahme für kommerzielle Nutzung. Für den verbindlichen Lizenztext sowie die genauen Bedingungen und Grenzen dieser Ausnahme siehe ausschließlich [`LICENSE`](./LICENSE).

---

<div align="center">

**Vibe** — Local control for AI-assisted software development.

</div>
