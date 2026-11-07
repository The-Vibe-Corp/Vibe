# vibe

Lokale Entwicklungszentrale für Projekte, Agenten, Modelle und MCP-Server.

## Projektgrundlagen

- SPEC.md: Produktumfang und verbindliche Anforderungen.
- TICKETS.md: priorisierte Arbeitspakete.
- AGENTS.md: Regeln für Implementierung, Tests und Review.
- FEEDBACK.md: neue Fehler und Nutzerbeobachtungen.
- docs/import-manifest.json: unverändert importierte Programmdateien.

## Dokumentation

- `docs/handbuch.md` — Bedienung der Oberfläche und der CLI.
- `docs/betrieb.md` — Pfade, Prozesse, Diagnose, Installation und Release.
- `docs/grenzen.md` — bekannte Grenzen und nicht zugesagte Funktionen.
- `docs/checkliste.md` — Abnahmecheckliste mit Versionen und Ergebnissen.
- `docs/abnahme-bazzite.md` — dokumentierte manuelle Bazzite-Prüfung.
- `docs/features/<ticket>.md` — fachliche und technische Dokumentation je
  Arbeitspaket; die Zuordnung zu Trilium steht in `docs/trilium-index.md`.

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

### Harness wählen (opencode oder Pi)

Der Coding-Harness führt die Arbeitspakete aus. Standard ist opencode; seit
AP04 ist Pi als erster alternativer Harness verfügbar. Die Auswahl lässt sich
beim Setup, über die CLI und in der Oberfläche ändern:

```
python3 scripts/setup-vibe.py --harness pi
vibe harness status
vibe harness use pi
vibe harness setup pi
```

Ohne gespeicherte Auswahl bleibt opencode der Standard. `vibe harness setup`
zeigt den offiziellen Bezug und den Installationsbefehl; Pi benötigt Node.js
22.19 oder neuer. In der Oberfläche steht die Auswahl in der Ansicht
„Umgebung“. Grenzen und die geprüften Pi-Aufrufe beschreibt
`docs/compatibility.md`.

### Vorschau, Update, Rollback und Uninstall

Die Vorschau zeigt Ziel, Version und jede Datei mit Aktion (`+` neu,
`~` sichern und ersetzen, `=` unverändert) und schreibt nichts:

    python3 scripts/setup-vibe.py --dry-run --vibe /pfad/zu/VibeCode

Ein Update sichert ersetzte Programmdateien und geänderte Nutzervorlagen unter
`_toolchain/backup-<Zeitstempel>/` und schreibt die Versionskennung nach
`_toolchain/version.json`. Solange ein Agentenlauf oder eine Dashboard-Sitzung
dieser Installation läuft, verweigert der Setup das Update; `--force` hebt die
Sperre nur nach ausdrücklicher Entscheidung auf:

    python3 scripts/setup-vibe.py --yes --update --vibe /pfad/zu/VibeCode
    python3 scripts/setup-vibe.py --yes --update --force --vibe /pfad/zu/VibeCode

Ein Rollback stellt die jüngste Sicherung wieder her; neu hinzugekommene
Dateien werden dabei entfernt:

    python3 scripts/setup-vibe.py --yes --rollback --vibe /pfad/zu/VibeCode
    python3 scripts/setup-vibe.py --yes --rollback --backup backup-20261102-101500 --vibe /pfad/zu/VibeCode

Uninstall entfernt Programmdateien, Vorlagen und die Versionskennung. Projekte,
Laufzeitdaten (`vibe.json`, `models.json`, `profiles.json`, `fritz.json`,
`costs.json`, `_logs`), Sicherungen und persönliche Konfiguration bleiben
erhalten:

    python3 scripts/setup-vibe.py --yes --uninstall --vibe /pfad/zu/VibeCode

Die Quellversion steht in `VERSION`, der zuletzt installierte Stand in
`_toolchain/version.json` (Version, Commit, Zeitpunkt, Modus, Quelle). Der
Setup meldet beides in der Vorschau und nach der Installation; fehlt `VERSION`,
lautet die Angabe ausdrücklich `unbekannt` statt geraten.

Windows kann die vibe-Dateien und die Oberfläche installieren. Agentenläufe
benötigen `tmux` und `flock` und damit WSL2 oder Docker; der Setup weist darauf
hin.

## Erster Auftrag

V-001 aus TICKETS.md bearbeiten.
Danach V-002, bevor funktionale Änderungen begonnen werden.
