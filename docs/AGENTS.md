# Agenten

Vibe verwaltet globale und projektspezifische KI-Agenten. Ein **globaler Agent** ist für alle Projekte verfügbar, ein **Project Agent** nur innerhalb eines einzelnen Projekts. [cite:1]

## Agenten verwalten

Im Dashboard kannst du Agenten:

- auflisten und filtern
- erstellen
- anzeigen
- bearbeiten
- kopieren
- löschen

Die Bearbeitung umfasst Beschreibung, Modus, Modell, Berechtigungen und Prompt — entweder über strukturierte Felder oder als Rohtext. [cite:1]

## Konfigurationsregeln

- Ungültige Eingaben verändern die bestehende Agent-Datei nicht.
- Namenskonflikte und Agent Shadowing werden sichtbar gemacht.
- Unbekannte Felder werden möglichst erhalten.
- Vor Änderungen werden Konfigurations-Backups erstellt und eine Wiederherstellung unterstützt. [cite:1]

## Rollen statt fester Namen

Vibe-Logik darf nicht von hartkodierten Agent-Namen abhängen. Coder und Reviewer werden über konfigurierbare Rollen zugewiesen. [cite:1]

| Rolle | Typischer Zweck |
|---|---|
| **Coder** | Implementiert ein Work Package |
| **Reviewer** | Prüft Ergebnis, Nachweise und technische Qualität |

## Modelle zuweisen

Agenten können Modelle aus verfügbaren Providern verwenden. Vibe unterscheidet dabei zwischen einem gelisteten Modell und einem Modell, für das der Nutzer tatsächlich autorisiert ist. [cite:1]

- Credentials gehören nicht in Agent-Dateien oder das Repository.
- Paid-Testanfragen erfordern vorherigen Hinweis und Zustimmung.
- Modell-IDs und Fähigkeiten werden nicht erfunden. [cite:1]

Details zu Modellen und Modellprofilen findest du in [docs/MODELS.md](docs/MODELS.md).

## Agent Runs

Ein **Agent Run** ist die Ausführung eines Work Packages über einen von Vibe unterstützten Harness. Vibe ist selbst kein AI Harness, sondern arbeitet mit externen, austauschbaren Harnesses über isolierte Ausführungs- und Konfigurationsschnittstellen. OpenCode ist ein unterstützter Harness. [cite:1]

Agent Runs können gestartet, beobachtet, angehängt und selektiv gestoppt werden. Das Dashboard zeigt Projekt, Agent, Startzeit, Session und aktuelles Work Package. [cite:1]

## Parallele Runs

Vibe unterstützt gleichzeitige Runs für unterschiedliche Projekte, ohne dass identische oder normalisierte Namen kollidieren. Live-Logs und separate Verifikationslogs sind verfügbar. [cite:1]

## Stoppen und Abschluss

- Das Schließen eines Browser-Tabs stoppt weder Vibe noch einen Agent Run.
- Ein erneutes Öffnen des Dashboards zeigt weiterhin laufende Sessions.
- Ein explizites Beenden über das Dashboard stoppt Vibe und seine verwalteten Agent Runs.
- Das Stoppen des Harness ist eine separate Aktion. [cite:1]

Vibe stoppt ausschließlich Prozesse, die eindeutig als Vibe-verwaltet identifiziert werden können. [cite:1]
