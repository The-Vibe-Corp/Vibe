# MCP-Server

Ein **MCP server** ist ein Dienst, der Tools über das Model Context Protocol bereitstellt. Vibe verwaltet globale und projektspezifische MCP-Server zentral. [cite:1]

## Verwaltung

Für MCP-Server kannst du:

- Server auflisten
- erstellen
- bearbeiten
- löschen
- aktivieren
- deaktivieren [cite:1]

## Lokale Server

Für lokale MCP-Server verwaltet Vibe:

- Executable
- Argumentliste
- Umgebungsvariablen [cite:1]

## Remote Server

Für remote MCP-Server verwaltet Vibe:

- URL
- Headers
- unterstützte Authentifizierung [cite:1]

## Konfigurationsschutz

Vibe dokumentiert die tatsächlichen Konfigurationsdateien und deren Precedence. Unbekannte Einstellungen und Kommentare werden möglichst erhalten. [cite:1]

Wenn eine Bearbeitung eine Datei nicht originalgetreu erhalten kann, stoppt Vibe oder fordert die Zustimmung zu einer konkreten Änderungsvorschau an. Daten werden niemals still verworfen. [cite:1]

## Secrets

Secrets werden maskiert, aber ihre Werte bleiben beim Speichern erhalten. Sie werden weder in Antworten, Fehlermeldungen, Command-Anzeigen noch Logs offengelegt. [cite:1]

## Verbindungstests

Vor einem Verbindungstest erklärt Vibe, dass dieser Programme starten oder Netzwerkverbindungen öffnen kann. Ein Connectivity Check ist nicht garantiert side-effect free. [cite:1]

Der Test prüft `initialize` und `tools/list`, zeigt die Server-Identität sowie verfügbare Tools und ruft funktionale Tools nicht automatisch auf. [cite:1]

## Fehlerklassen

Vibe unterscheidet unter anderem:

- Fehlende Executables
- Timeouts
- DNS- und TLS-Fehler
- HTTP-Fehler
- Authentifizierungsfehler
- Protokollfehler
- Ungültige Konfiguration [cite:1]

Unterstützte Transports werden explizit angezeigt. Ein nicht unterstützter Transport bedeutet nicht, dass der Server defekt ist. [cite:1]

## Ressourcenschutz

Verbindungstests begrenzen Ausführungszeit, Output und Ressourcennutzung. Testprozesse und ihre Kinder werden zuverlässig gestoppt. [cite:1]

Ein erfolgreicher Verbindungstest bedeutet nicht, dass ein Agent jedes gelistete Tool verwenden darf. Agent-spezifische Berechtigungen müssen sichtbar oder nachvollziehbar sein. [cite:1]
