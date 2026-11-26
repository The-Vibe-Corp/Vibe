# Konfiguration

Vibe trennt Quellcode, Installation und Laufzeitdaten. Einstellungen, Logs, Tokens, Backups und Statusdaten gehören zu den Laufzeitdaten und werden nicht im Quellcode-Repository verwaltet. [cite:1]

## Workspace

`$VIBE` identifiziert den Vibe-Workspace. Er ist der zentrale Ort für die von Vibe verwalteten Laufzeitdaten. [cite:1]

```bash
export VIBE="$HOME/vibe-workspace"
```

## Datenmodell

| Ebene | Inhalt | Behandlung |
|---|---|---|
| **Project source** | Quellcode im Git-Repository | Bleibt im jeweiligen Projekt |
| **Installation** | Deployed, ausführbare Vibe-Anwendung | Wird durch Installation und Update verwaltet |
| **Runtime data** | Einstellungen, Logs, Tokens, Backups, Status | Bleibt lokal im Workspace |

Diese Trennung ist verbindlich: Ein Update einer Ebene darf die anderen nicht überschreiben. [cite:1]

## Projekte

Vibe kann Entwicklungverzeichnisse verwalten und Projekte über Git-Metadaten oder eine Vibe-Projektkonfiguration erkennen. Projekte mit gleichem Namen in unterschiedlichen Verzeichnissen werden unterschieden. [cite:1]

- Entwicklungverzeichnisse hinzufügen, entfernen und neu scannen.
- Projektliste mit Name, Typ, Branch, Änderungen, offenen Work Packages, Run-Status und letztem Commit.
- Projekt-Detailansicht mit Pfad, Feedback, Tickets, Logs und verfügbaren Aktionen.
- Ungeeignete, zu breite oder nicht erlaubte Pfade werden mit klarer Begründung abgelehnt. [cite:1]

## Projekt-Templates

Vibe bietet Vorlagen für gängige Projekttypen, beispielsweise generische Projekte, Android und Web. Weitere Projekttypen können über Templates ergänzt werden. [cite:1]

Templates bereiten bestehende Projekte vor, ohne Dateien still zu überschreiben. Fehler bei Projekterstellung oder Git-Initialisierung werden klar gemeldet. Projekttypen können eigene Verifikations-Adapter bereitstellen. [cite:1]

## Tickets und Work Packages

Tickets — einschließlich Work Packages, Bugs und Feedback — werden in einem lokalen, nicht versionierten und maschinenlesbaren Store gespeichert: `.vibe/tickets.json`. [cite:1]

Unterstützte Status:

- `draft`
- `open`
- `in-progress`
- `blocked`
- `awaiting-merge`
- `completed`

IDs werden automatisch vergeben, sofern keine eigene ID angegeben wird. Sie müssen auch bei gleichzeitigen Schreibvorgängen eindeutig bleiben. [cite:1]

## Migration

Bei der Übernahme bestehender Installationen müssen `_toolchain`- und `_logs`-Daten erhalten bleiben. Persönliche Konfiguration darf nicht durch ausgelieferte Defaults ersetzt werden. [cite:1]

Vor einer Migration werden Vorschau und Backup bereitgestellt. Updates und Rollbacks erhalten persönliche Einstellungen; eine Deinstallation entfernt standardmäßig weder Projekte noch Nutzerdaten. [cite:1]
