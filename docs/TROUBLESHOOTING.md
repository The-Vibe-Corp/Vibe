# Troubleshooting

Vibe bietet Diagnostics, um Probleme früh zu erkennen und konkrete Remediation-Schritte bereitzustellen. [cite:1]

## Diagnostics prüfen

Diagnostics unterscheiden zwischen:

- Anwendungs-Voraussetzungen
- optionalen Projekt-Tools
- Host-/Container-Mismatch
- Schreibrechten
- Portverfügbarkeit
- erforderlichen Programmen [cite:1]

Fehlende optionale Komponenten dürfen die Kernfunktionalität nicht still beschädigen. [cite:1]

## Häufige Probleme

| Problem | Mögliche Ursache | Nächster Schritt |
|---|---|---|
| Dashboard nicht erreichbar | Vibe läuft nicht oder Port ist belegt | Diagnostics und Portverfügbarkeit prüfen |
| Agent Run startet nicht | Fehlende Verifikationskonfiguration oder Harness-Problem | Verifikationskonfiguration und Harness-Logs prüfen |
| MCP-Verbindung schlägt fehl | Executable fehlt, Timeout, DNS/TLS-, HTTP-, Auth- oder Protokollfehler | Verbindungstest und Fehlerklasse prüfen |
| Modell nicht nutzbar | Modell gelistet, aber keine Autorisierung | Provider-Zugang und Credentials prüfen |
| Ticket lässt sich nicht abschließen | Akzeptanzkriterien oder Nachweise fehlen | Akzeptanzkriterien und Verifikationsnachweise ergänzen |
| Update überschreibt Einstellungen | Nicht erwartet; persönliche Einstellungen müssen erhalten bleiben | Backup prüfen und Issue melden |

## Logs

Vibe stellt Live-Logs und separate Verifikationslogs bereit. Diese helfen dabei, Agent Runs, Verifikation und Fehler getrennt nachzuvollziehen. [cite:1]

## Agent Runs

- Quota- und Login-Fehler stoppen einen Run sofort.
- Retry-Limits gelten nur für andere, wiederholbare Fehlerklassen.
- Externe Signale wie `HUP`, `TERM` oder `INT` erzeugen einen Trace, einen Log-Eintrag und eine Aktualisierung des Run-Registry-States. [cite:1]

## MCP-Fehler

Ein erfolgreicher Verbindungstest bedeutet nicht, dass ein Agent jedes gelistete Tool verwenden darf. Agent-spezifische Berechtigungen müssen sichtbar oder nachvollziehbar sein. [cite:1]

## Sichere Fehlerbehebung

- Ändere zunächst eine separate Test-Instanz, nicht die Produktionsinstallation.
- Starte während eines Agent Runs kein Update der laufenden Instanz.
- Erstelle vor Migration oder riskanten Änderungen ein Backup.
- Teile keine Tokens, API-Keys oder anderen Secrets in Issues, Logs oder Screenshots. [cite:1]
