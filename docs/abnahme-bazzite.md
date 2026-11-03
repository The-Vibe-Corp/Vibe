# Manuelle Bazzite-Abnahme

Stand: 2026-11-03
Gilt für: vibe 0.18.0 (Repositorystand, siehe `VERSION`)

Diese Datei dokumentiert die manuelle Abnahme auf dem Bazzite-Host. Sie ist
kein Ersatz für die automatisierten Tests, sondern belegt die Fälle, die nur
mit einem echten Host, einem echten Container und einem echten Startmenü
sinnvoll prüfbar sind.

## Prüfumgebung

| Komponente | Stand am 2026-11-03 |
| --- | --- |
| Host | Bazzite 44.20261026.0 (Kinoite), `ostree-image-signed:docker://ghcr.io/ublue-os/bazzite-nvidia-open:stable` |
| Host-Kernel | 7.2.11-ogc4.1.fc44.x86_64 |
| Steuerungscontainer | Fedora Linux 44 (Toolbx), `registry.fedoraproject.org/fedora-toolbox:latest` |
| podman | 5.8.9 |
| distrobox | 1.8.2.5 |
| tmux | 3.8 |
| flock | util-linux 2.41.5 |
| Python | 3.14.8 |
| opencode | 2.2.5 (geprüft ist 2.1.4, siehe `docs/compatibility.md`) |
| Playwright | 1.63.0 |
| Chromium | Google Chrome for Testing 153.0.8010.12 |
| desktop-file-validate | 0.28 |

Die Versionsangaben wurden mit `cat /etc/os-release`, `uname -r`,
`podman --version`, `distrobox --version`, `tmux -V`, `flock --version`,
`python3 --version`, `opencode --version`, `importlib.metadata.version`
und `desktop-file-validate --version` erhoben. Der Host wurde über
`distrobox-host-exec` befragt.

## Abnahme vom 2026-11-02 (V-017)

Die Host-Abnahme des Starters lief mit einem separaten Testcontainer
`vibe-v017-accept`, dem Dev-Profil, Port 8788 und einem Arbeitsbereich mit
Leerzeichen, Umlaut, `$`, Apostroph und Klammern. Browser und Notifier waren
Attrappen; die aufgerufenen Programme und Argumente wurden real ausgeführt.
Die produktive Instanz (`vibe-ui`, Port 8787, Container `android-dev`) blieb
während der gesamten Abnahme unverändert.

| Fall | Ergebnis |
| --- | --- |
| Container aus, Dashboard aus | Starter startet den Container, das Dashboard und öffnet den Browser mit Token |
| Dashboard läuft, zweiter Klick | nur Browser, keine zweite Sitzung, identische URL |
| Doppelklick (zwei parallele Starter) | genau eine Dashboard-Sitzung, zwei Browseraufrufe |
| Tokenwechsel nach Stop/Start | neues Token, neue URL, altes Token erscheint nicht |
| Fremder Dienst auf Port 8789 | Exit 1, Meldung „fremder Dienst“, kein Browser |
| Startfehler (CLI Exit 3) | Exit 1, stderr, Notifier, bereinigtes Log, kein Browser |
| Menüaktion stop | nur `vibe-ui-dev` beendet; `vibe-ui`, Port 8787 und Container bleiben |
| Stop ohne Dashboard | Exit 0, „vibe läuft nicht; nichts beendet.“ |
| Desktopdatei | `desktop-file-validate` Exit 0 für normale und für Pfade mit Leerzeichen, `$`, Apostroph und Klammern |

Das vollständige Protokoll dieser Abnahme liegt unter
`docs/features/V-017-bazzite.txt`; es endet mit „ERGEBNIS: 0 Fehler“.

## Nachprüfung vom 2026-11-03

Nach Abschluss der Dokumentations- und Releasearbeiten wurden die
schreibgeschützten Host-Zustände erneut geprüft. Es wurden keine Container
gestartet oder beendet und keine produktiven Dateien geändert.

| Prüfung | Befehl | Beobachtetes Ergebnis |
| --- | --- | --- |
| Produktives Dashboard | `curl -fsS http://127.0.0.1:8787/api/health` | HTTP 200, `{"ok": true, "app": "vibe", "api": 1, "instance": "6a6dac450d2ae7bc", "bind": "127.0.0.1", "port": 8787, "pid": 161044, "started": "2026-11-03T17:44:27Z"}` |
| Starter-Status | `python3 scripts/vibe_starter.py status` | `vibe läuft: http://127.0.0.1:8787/`, Exit 0 |
| Desktopdatei | `desktop-file-validate ~/.local/share/applications/vibe.desktop` | Exit 0 |
| Releaseanzeige der Quelle | `python3 bin/vibe doctor` | `Release: Version 0.18.0 · Commit f245113 · Installation` |

Die produktive Instanz antwortet weiterhin mit der alten Health-Form ohne
Releasefelder. Das ist erwartbar: Sie läuft noch auf dem Stand vor diesem
Arbeitspaket. Die Felder `version`, `commit` und `release_origin` erscheinen
erst nach einer Installation oder einem Update des neuen Stands. Die
Quellprüfung mit `vibe doctor` liest die Kennung der vorhandenen Installation
(`_toolchain/version.json`) und meldet deshalb `Commit f245113`.

## Was nicht erneut geprüft wurde

- Der Fall „Container aus, Dashboard aus“ wurde am 2026-11-02 mit dem
  Testcontainer `vibe-v017-accept` geprüft und am 2026-11-03 nicht wiederholt.
  `android-dev` kann nicht gestoppt werden, weil diese Entwicklungssitzung
  selbst darin läuft.
- Die Desktopdatei wurde statisch validiert, aber nicht in einer echten
  GNOME-Shell angeklickt.
- Die Bazzite-Abnahme verwendet Attrappen für Browser und Notifier. Echte
  Fenster und Benachrichtigungen sind nicht Teil des Nachweises.
- Es wurden keine echten Modellkosten, OAuth-Anmeldungen oder produktiven
  MCP-Aufrufe ausgelöst.

## Aufräumhinweis

Im Benutzerprofil liegt aus der V-017-Abnahme die Datei
`~/.local/share/applications/vibe-v017-accept.desktop`. Sie enthält eine
ungültige Kategorie `Categories=Distrobox;System;Utility` und gehört nicht zur
produktiven Installation. Die Datei wurde im Rahmen dieses Arbeitspakets nicht
gelöscht, weil sie außerhalb des Repositorys im persönlichen Profil liegt.
Sie kann gefahrlos entfernt werden:

```
rm ~/.local/share/applications/vibe-v017-accept.desktop
```

## Verwandte Dokumente

- `docs/features/V-017.md` — technische Umsetzung und Grenzen des Starters.
- `docs/features/V-017-bazzite.txt` — Rohprotokoll der Host-Abnahme.
- `docs/checkliste.md` — vollständige Abnahmecheckliste mit Testzahlen.
- `docs/betrieb.md` — Betrieb, Diagnose, Installation und Release.
