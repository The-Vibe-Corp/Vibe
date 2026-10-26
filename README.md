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

Universeller, interaktiver Setup (Linux, Container, Windows):

    python3 scripts/setup-vibe.py

Unter Windows:

    setup-vibe.cmd

Der Setup erkennt Ubuntu/Debian, Fedora, Bazzite, Container (Docker/Podman/
Toolbx/Distrobox) und Windows, prüft die Werkzeuge und bietet fehlende
Pakete nur mit Zustimmung an. Eine bestehende Installation wird standardmäßig
wiederverwendet; `--update` ersetzt Programmdateien mit Sicherung. Laufzeitdaten
(`vibe.json`, `models.json`, `profiles.json`, `fritz.json`, `_logs`) und
vorhandene `.vibe/project.env` werden nie überschrieben.

Der bisherige Einstieg bleibt kompatibel:

    VIBE=/pfad/zu/VibeCode bash install-vibe.sh

Nicht-interaktive Varianten und Vorschau:

    python3 scripts/setup-vibe.py --yes --vibe /pfad/zu/VibeCode
    python3 scripts/setup-vibe.py --dry-run --vibe /pfad/zu/VibeCode
    python3 scripts/setup-vibe.py --yes --install-deps --vibe /pfad/zu/VibeCode

Windows kann die vibe-Dateien und die Oberfläche installieren. Agentenläufe
benötigen `tmux` und `flock` und damit WSL2 oder Docker; der Setup weist darauf
hin. Reproduzierbare Installation und Rollback im Sinne von V-018 bleiben ein
eigenes Arbeitspaket.

## Erster Auftrag

V-001 aus TICKETS.md bearbeiten.
Danach V-002, bevor funktionale Änderungen begonnen werden.
