# vibe

Lokale Entwicklungszentrale für Projekte, Agenten, Modelle und MCP-Server.

## Projektgrundlagen

- SPEC.md: Produktumfang und verbindliche Anforderungen.
- TICKETS.md: priorisierte Arbeitspakete.
- AGENTS.md: Regeln für Implementierung, Tests und Review.
- FEEDBACK.md: neue Fehler und Nutzerbeobachtungen.
- docs/import-manifest.json: unverändert importierte Programmdateien.

## Ausgangsbasis

Der Quellcode wurde aus der funktionierenden lokalen Installation übernommen.
Die Bestandsaufnahme und reproduzierbare Testumgebung sind die ersten Tickets.

## Entwicklung

Im Distrobox-Container android-dev.
Nicht direkt an der produktiven Installation unter _toolchain entwickeln.
Bis V-006 existiert, keine ungeprüften Dev-Starts mit produktiven HOME-/VIBE-Pfaden.

## Tests

V-002 richtet folgende Kommandos ein:

    bash scripts/verify.sh quick
    bash scripts/verify.sh full

## Installation

Die produktive Installation bleibt während der Projektübernahme unverändert.
Reproduzierbare Installation und Rollback werden in V-018 umgesetzt.

## Erster Auftrag

V-001 aus TICKETS.md bearbeiten.
Danach V-002, bevor funktionale Änderungen begonnen werden.
