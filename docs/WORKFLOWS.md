# Workflows

Vibe koordiniert den Weg von Anforderung zu integrierter Änderung: Tickets, Work Packages, Agent Runs, Verifikation und Abschlussaktionen werden von einem Runner verwaltet. [cite:1]

## Begriffe

| Begriff | Bedeutung |
|---|---|
| **Ticket** | Work Package, Bug oder Feedback |
| **Work Package** | Eine abgegrenzte Arbeitseinheit mit Ziel und Akzeptanzkriterien |
| **Agent Run** | Ausführung eines Work Packages über einen unterstützten Harness |
| **Runner** | Vibe-verwalteter Prozess für Work Packages, Git-Workspaces, Verifikation und Abschluss |
| **Verification** | Funktionsprüfung eines Pakets oder des Integrationsstands |

Diese Begriffe sind Teil der verbindlichen Produktspezifikation. [cite:1]

## Ticket-Lebenszyklus

Tickets werden lokal, unversioniert und maschinenlesbar in `.vibe/tickets.json` gespeichert. [cite:1]

```text
draft → open → in-progress → blocked / awaiting-merge → completed
```

Nutzer können Feedback hinzufügen sowie Work Packages erstellen, bearbeiten und löschen. IDs werden automatisch vergeben, sofern keine eigene ID angegeben wird. [cite:1]

## Akzeptanz und Nachweise

Ein Work Package gilt erst dann als abgeschlossen, wenn:

- die Akzeptanzkriterien erfüllt sind,
- geeignete Nachweise vorliegen,
- ein Commit allein nicht als Akzeptanznachweis ausreicht,
- ein blockiertes Ticket nicht als complete gilt. [cite:1]

Der Runner validiert Nachweise aus der Ticket-Working-Copy und aktualisiert den Ticket-Store. Dass ein Agent seine Arbeit beendet hat, bedeutet nicht, dass das Paket integriert wurde. [cite:1]

## Paket-Übergabe und Abschluss

Paket-Übergabe und Abschluss sind getrennte Schritte. [cite:1]

### Lokaler Modus

Im lokalen Modus merged der Runner ein akzeptiertes Paket in den lokalen Integration Branch und bereinigt anschließend Package Worktree und Branch. [cite:1]

### GitHub-Modus

Im GitHub-Modus holt der Runner den aktuellen Integrationsstand und merged ihn vor dem Push in den Feature Branch. Konflikte werden im Package Worktree aufgelöst. [cite:1]

## Pull Requests

Ohne Auto-Merge öffnet der Runner einen Pull Request und wartet auf manuelles Mergen sowie Abschlussbestätigung. Der Worktree bleibt in dieser Zeit registriert. [cite:1]

Mit aktiviertem Auto-Merge kann der Runner einen genehmigten Pull Request nach bestandenen Gates squash-mergen. Finale Synchronisation und Cleanup folgen der bestätigten Merge. [cite:1]

Automatisches Publizieren, Pushen, Mergen oder Releasen erfolgt nicht ohne Autorisierung. Automatisches GitHub-Merging erfordert eine konfigurierte Opt-in-Einstellung. [cite:1]

## Verifikation

Paketverifikation und vollständige Verifikation des Integrationsstands sind separate Runner-Gates. Checks werden pro Projekt konfiguriert; Agenten können die konfigurierten Gate-Commands während eines Runs nicht ersetzen. [cite:1]

- Fehlende Verifikationskonfiguration ist ein Fehler, kein erfolgreicher Check.
- Retry- und Iterationslimits sind konfigurierbar.
- Ein Iterationslimit ist kein Spending Budget und darf nicht so bezeichnet werden. [cite:1]

## Fehler und Stopps

Quota- und Login-Fehler stoppen einen Run sofort. Retry-Limits gelten nur für andere, wiederholbare Fehlerklassen. [cite:1]

Externe Signale wie `HUP`, `TERM` oder `INT` beenden einen Run nicht ohne Trace. Vibe protokolliert das Signal, einen Log-Eintrag und den Run-Registry-State. [cite:1]

Beim Start werden orphaned `running`-Einträge des aktuellen Projekts als extern terminiert markiert. Sessions anderer Projekte, aktive Sessions und Sessions mit unklarem Zustand bleiben unverändert. [cite:1]
