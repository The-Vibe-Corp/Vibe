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
- `docs/features/README.md` — index of features: current behavior per
  feature plus per-package records.

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
(`vibe.json`, `models.json`, `profiles.json`, Logverzeichnis) und
vorhandene `.vibe/project.env` werden nie überschrieben.

### Verzeichnisse: Workspace, Installationsort, Logs

Der Setup fragt drei Orte getrennt ab. Jeder Ort lässt sich einzeln wählen;
die Vorschläge entsprechen der bisherigen Anordnung unter `~/VibeCode`.

| Rolle | Inhalt | Option | Umgebungsvariable | Standard |
|---|---|---|---|---|
| Workspace | Projektordner (Git-Repositories) | `--vibe` oder `--workspace` | `VIBE` | `~/VibeCode` |
| Installationsort | Programme, Vorlagen, Versionskennung, Sicherungen, persönliche Einstellungen | `--install` | `VIBE_INSTALL` | `<Workspace>/_toolchain` |
| Logverzeichnis | Logs, `runs.json`, Laufzeitzustand | `--logs` | `VIBE_RUNTIME` | `<Workspace>/_logs` |

Regeln: Installationsort und Workspace dürfen nicht identisch sein, und der
Workspace darf nicht im Installationsort liegen. Das Logverzeichnis ist weder
Workspace noch Installationsort und enthält beide nicht. Der Installationsort
und das Logverzeichnis dürfen innerhalb des Workspace liegen. Der Quellordner
des Setups ist als Ziel ausgeschlossen. Der Zustand (`vibe.json`,
`profiles.json`, `limits.json`) liegt wie bisher im
Installationsort.

Der Setup trägt die Auswahl nach erfolgreicher Installation in
`~/.config/vibe/config.json` unter `profiles.prod` ein (`workspace`, `install`
und nur bei abweichendem Ort `runtime`). Andere Einstellungen der Datei bleiben
erhalten; eine vorhandene Datei wird vorher als `config.json.bak-<Zeitstempel>`
gesichert, eine ungültige Datei wird nicht verändert. Umgebungsvariablen haben
Vorrang vor der Konfiguration; weicht eine gesetzte Variable ab, weist der
Setup darauf hin. Das Dev-Profil bleibt davon unberührt. Die Priorität der
Konfiguration beschreibt `docs/betrieb.md`.

Beispiel mit drei getrennten Orten:

    python3 scripts/setup-vibe.py \
        --vibe ~/projects \
        --install ~/.local/share/vibe \
        --logs ~/.local/state/vibe

Bei einer bestehenden Installation unter `~/VibeCode/_toolchain` genügt es, die
Vorschläge zu bestätigen; es ändert sich nichts. Wer den Installationsort
wechselt, muss persönliche Dateien (`vibe.json`, `profiles.json`)
selbst in den neuen Ort kopieren, oder `state` in der
Konfiguration auf den alten Ort setzen.

Der bisherige Einstieg bleibt kompatibel:

    VIBE=/pfad/zu/VibeCode bash install-vibe.sh

Nicht-interaktive Varianten und Vorschau:

    python3 scripts/setup-vibe.py --yes --vibe /pfad/zu/workspace
    python3 scripts/setup-vibe.py --yes --vibe /pfad/zu/workspace --install /pfad/zu/install --logs /pfad/zu/logs
    python3 scripts/setup-vibe.py --dry-run --vibe /pfad/zu/workspace
    python3 scripts/setup-vibe.py --yes --install-deps --vibe /pfad/zu/workspace

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

### Limitverhalten (global)

Quota- und Anmeldefehler halten einen Agentenlauf standardmäßig sofort an.
Das Verhalten gilt global für alle Projekte und lässt sich ausdrücklich
ändern:

```
vibe limits status
vibe limits continue
vibe limits stop
```

`stop` ist die Voreinstellung (auch ohne Einstellungsdatei). `continue`
behandelt Quota- und Anmeldefehler wie wiederholbare Fehler im Rahmen der
vorhandenen Wiederholungslimits und protokolliert einen Hinweis; es werden
keine Dienstlimits umgangen und keine unbegrenzten Wiederholungen gestartet.
Die Einstellung liegt in `<Zustand>/limits.json`; eine defekte Datei wird
gemeldet und wie `stop` ausgelegt.

### Vorschau, Update, Rollback und Uninstall

Die Vorschau zeigt Workspace, Installationsort, Logverzeichnis, die geplante
Konfigurationsänderung, die Version und jede Datei mit Aktion (`+` neu,
`~` sichern und ersetzen, `=` unverändert) und schreibt nichts:

    python3 scripts/setup-vibe.py --dry-run --vibe /pfad/zu/workspace

Ein Update sichert ersetzte Programmdateien und geänderte Nutzervorlagen unter
`<Installationsort>/backup-<Zeitstempel>/` und schreibt die Versionskennung nach
`<Installationsort>/version.json`. Solange ein Agentenlauf (`runs.json` im Logverzeichnis) oder eine
Dashboard-Sitzung dieser Installation läuft, verweigert der Setup das Update; `--force` hebt die
Sperre nur nach ausdrücklicher Entscheidung auf:

    python3 scripts/setup-vibe.py --yes --update --vibe /pfad/zu/workspace
    python3 scripts/setup-vibe.py --yes --update --force --vibe /pfad/zu/workspace

Ein Rollback stellt die jüngste Sicherung wieder her; neu hinzugekommene
Dateien werden dabei entfernt:

    python3 scripts/setup-vibe.py --yes --rollback --vibe /pfad/zu/workspace
    python3 scripts/setup-vibe.py --yes --rollback --backup backup-20261102-101500 --vibe /pfad/zu/workspace

Uninstall entfernt Programmdateien, Vorlagen und die Versionskennung. Projekte,
Laufzeitdaten (`vibe.json`, `models.json`, `profiles.json`,
`costs.json`, Logverzeichnis), Sicherungen und persönliche Konfiguration bleiben
erhalten:

    python3 scripts/setup-vibe.py --yes --uninstall --vibe /pfad/zu/workspace

Die Quellversion steht in `VERSION`, der zuletzt installierte Stand in
`<Installationsort>/version.json` (Version, Commit, Zeitpunkt, Modus, Quelle). Der
Setup meldet beides in der Vorschau und nach der Installation; fehlt `VERSION`,
lautet die Angabe ausdrücklich `unbekannt` statt geraten.

Rollback, Uninstall und Update fragen dieselben drei Orte ab (oder lesen sie aus
Optionen und Konfiguration); `--install` und `--logs` sind dafür ebenfalls
gültig. Unter Windows liegt `vibe.cmd` im Installationsort.

Windows kann die vibe-Dateien und die Oberfläche installieren. Agentenläufe
benötigen `tmux` und `flock` und damit WSL2 oder Docker; der Setup weist darauf
hin.

## Erster Auftrag

V-001 aus TICKETS.md bearbeiten.
Danach V-002, bevor funktionale Änderungen begonnen werden.

## Lizenz

Dieses Projekt ist unter der GNU Affero General Public License Version 3
(AGPL-3.0-only) veröffentlicht. Der vollständige, unveränderte kanonische
Lizenztext und die Projekt-Attribution stehen in `LICENSE`.

Privatnutzung und AGPL-konforme Nutzung kostenlos; proprietär bzw. kommerzielle Nutzung ohne AGPL-Pflichten erfordert eine kommerzielle Lizenz.

Wir stellen die Software Privatpersonen und allen, die die Copyleft-Pflichten
der AGPLv3 akzeptieren, kostenlos bereit (siehe `LICENSE`). Unternehmen, die
sie proprietär bzw. ohne Copyleft-Offenlegung nutzen wollen, kaufen eine
separate kommerzielle Lizenz von uns.

## Mitwirken und Lizenz

Beiträge: siehe `CONTRIBUTING.md`, Verhaltensregeln in
`CODE_OF_CONDUCT.md`. Sicherheitsmeldungen bitte nicht öffentlich — siehe
`SECURITY.md`. Die Lizenzierung folgt dem Dual-Licensing-Modell oben; der
vollständige Lizenztext steht in `LICENSE`.
