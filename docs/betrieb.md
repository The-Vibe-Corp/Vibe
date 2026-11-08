# Betrieb und Diagnose

Stand: 2026-11-03
Gilt für: vibe 0.18.0 (Repositorystand, siehe `VERSION`)

Diese Anleitung beschreibt Pfade, Prozesse, Ports, Sicherungen, Installation,
Release und die Diagnose. Die tägliche Bedienung steht in `docs/handbuch.md`;
bekannte Grenzen in `docs/grenzen.md`.

## Pfade und Profile

vibe trennt vier Rollen. Sie dürfen nicht vermischt werden:

| Rolle | Standard | Inhalt |
| --- | --- | --- |
| Quellen | `$VIBE/_toolchain` (installiert) bzw. das Repository (Entwicklung) | laufender Programmcode |
| Installation | `$VIBE/_toolchain` | Programme, Vorlagen, Prüfskripte, Katalog |
| Laufzeit | `$VIBE/_logs` | Logs, Token, Instanzkennung, Pause-Markierungen |
| Zustand | `$VIBE/_toolchain` | `vibe.json`, `profiles.json`, `fritz.json`, `costs.json`, Sicherungen |

Profile:

| Profil | Arbeitsbereich | Dashboard | opencode | tmux |
| --- | --- | --- | --- | --- |
| `prod` | `~/VibeCode` | 8787 | 4096 | `vibe-ui`, `vibe-<projekt>` |
| `dev` | `~/VibeCode-dev` | 8788 | 4097 | `vibe-ui-dev`, `vibe-<projekt>-dev` |

`vibe paths [prod|dev] [--json]` zeigt die aufgelösten Pfade und Ports, ohne
etwas anzulegen oder zu starten. Konfigurationspriorität (niedrig nach hoch):

1. mitgelieferte Defaults,
2. `~/.config/vibe/config.json` (oder `$XDG_CONFIG_HOME`, `$VIBE_CONFIG_FILE`,
   `$VIBE_CONFIG_DIR`),
3. Umgebungsvariablen (`VIBE`, `VIBE_PROFILE`, `VIBE_INSTALL`, `VIBE_RUNTIME`,
   `VIBE_STATE`, `VIBE_UI_PORT`, `VIBE_OPENCODE_PORT`, `VIBE_UI_BIND`,
   `VIBE_CONTAINER`, `VIBE_AGENTS_DIR`),
4. ausdrückliche Übergaben.

Das Dev-Profil verweigert Pfade, die mit dem produktiven Arbeitsbereich
geteilt werden. Damit kann ein Entwicklungslauf die laufende Instanz nicht
beschreiben.

## Prozesse und Ports

- Das Dashboard bindet ausschließlich an Loopback (Standard `127.0.0.1`).
- Der Starter erkennt eine echte Instanz über `/api/health` (App, Instanz-ID,
  Port). Ein fremder Dienst auf dem Port wird nicht übernommen.
- Verwaltete tmux-Sitzungen tragen `VIBE_MANAGED=ui` bzw. `VIBE_MANAGED=run`.
  Nur eindeutig verwaltete Sitzungen werden beendet.
- Der Browser-Tab ist keine Hintergrundressource: Schließen beendet weder
  Dashboard noch Läufe.
- `vibe server start|stop|status` verwaltet den gemeinsamen
  opencode-Server getrennt vom Dashboard.

## Token und Zugriffsschutz

- Das Dashboard-Token steht in `$VIBE/_logs/web.token` und wird beim Start neu
  erzeugt. Die Datei wird, soweit das Dateisystem es unterstützt, mit Modus
  `0600` geschrieben. Auf FUSE/NTFS sind Unix-Rechte nicht zusicherbar.
- Die Start-URL enthält das Token im Fragment (`#t=...`); das Fragment wird
  nicht an den Server gesendet.
- Schreibende API-Aufrufe verlangen das Token; zusätzlich werden Host und
  Origin geprüft. Das Token erscheint nicht in Logs oder Fehlermeldungen.
- `/api/health` ist ohne Token lesbar und enthält keine Geheimnisse.

## Logs und Laufzeitdaten

| Datei | Bedeutung |
| --- | --- |
| `$VIBE/_logs/<projekt>.log` | Lauf-Log des Agenten |
| `$VIBE/_logs/<projekt>.verify.log` | Prüfprotokoll (quick/full) |
| `$VIBE/_logs/web.token` | aktuelles Dashboard-Token |
| `$VIBE/_logs/web.instance` | Instanzkennung des Dashboards |
| `$VIBE/_logs/<projekt>.pause-after` | einmalige Pause-Anforderung |

Lauf- und Prüflogs werden ab 5 MiB rotiert; es bleiben höchstens drei Archive
(`.1` bis `.3`). Die Rotation ist best effort und ersetzt keine
Datensicherung.

## Installation, Update, Rollback und Uninstall

Alle Aktionen lassen sich zuerst als Vorschau ausgeben:

```
python3 scripts/setup-vibe.py --dry-run --vibe /pfad/zu/VibeCode
python3 scripts/setup-vibe.py --yes --update --vibe /pfad/zu/VibeCode
python3 scripts/setup-vibe.py --yes --rollback --vibe /pfad/zu/VibeCode
python3 scripts/setup-vibe.py --yes --uninstall --vibe /pfad/zu/VibeCode
```

| Aktion | Wirkung | Bleibt erhalten |
| --- | --- | --- |
| Vorschau | zeigt Ziel, Version und je Datei `+`, `~`, `=`; schreibt nichts | alles |
| Erstinstallation | kopiert Programme, Vorlagen, Webdateien, `VERSION` | vorhandene Nutzerdaten |
| Update | sichert ersetzte Dateien und geänderte Nutzervorlagen unter `_toolchain/backup-<Zeitstempel>/` | Laufzeitdaten, `.vibe/project.env`, Sicherungen |
| Rollback | stellt die jüngste oder eine benannte Sicherung wieder her; entfernt neu hinzugekommene Dateien | Laufzeitdaten |
| Uninstall | entfernt Programme, Vorlagen und `version.json` | Projekte, Laufzeitdaten, Sicherungen, persönliche Konfiguration |

Ein Update ist gesperrt, solange ein Agentenlauf oder eine Dashboard-Sitzung
dieser Installation läuft. Ein Registereintrag zählt dabei nur, wenn seine
tmux-Sitzung tatsächlich existiert; verwaiste Einträge ohne Sitzung blockieren
nicht. `vibe runs prune` markiert solche Einträge als beendet, auch wenn das
Projektverzeichnis fehlt, und beendet niemals eine Sitzung. Ist tmux nicht
prüfbar, bleiben die Einträge unverändert und werden als „nicht prüfbar“
gemeldet. `--force` hebt die Sperre nur nach ausdrücklicher Entscheidung auf. Die Versionskennung steht in `_toolchain/version.json`
(Version, Commit, Zeitpunkt, Modus, Quelle); fehlt `VERSION`, lautet die Angabe
ausdrücklich `unbekannt`.

## Release bauen und prüfen

Eine Release wird ausschließlich aus versionierten Dateien eines Git-Stands
gebaut. Unversionierte Laufzeitdaten, Sicherungen, Tokens und Logs gelangen
dadurch nicht in das Archiv. Jeder Text wird zusätzlich auf absolute
Home-Pfade und die Muster der Geheimnisprüfung untersucht.

```
python3 scripts/build-release.py --output /tmp/vibe-release
python3 scripts/build-release.py verify /tmp/vibe-release/vibe-0.18.0-<commit>.tar.gz
```

Eigenschaften:

- Dateiname `vibe-<version>-<commit>.tar.gz`, daneben `<archiv>.sha256`.
- `RELEASE.json` im Archiv nennt Version, vollständigen und kurzen Commit,
  Referenz sowie SHA-256, Größe und Modus jeder Datei.
- Zwei Baue desselben Commits sind byte-identisch: sortierte Einträge, fester
  Zeitstempel, fester Benutzer und feste Gruppe, gzip ohne Zeitstempel.
- `verify` lehnt fehlende oder zusätzliche Dateien, abweichende Prüfsummen,
  unsichere Pfade und ausgeschlossene Dateien ab.
- Der Bau bricht ab, wenn eine versionierte Datei einem Ausschlussmuster
  entspricht (z. B. versehentlich versioniertes `web.token`), damit nichts
  stillschweigend fehlt.

Reproduzieren:

```
git checkout <commit>
python3 scripts/build-release.py --output /tmp/release-a
python3 scripts/build-release.py --output /tmp/release-b
sha256sum /tmp/release-a/*.tar.gz /tmp/release-b/*.tar.gz
```

## Diagnose

Reihenfolge bei Problemen:

1. `vibe doctor` — Container, Schreibbarkeit, Werkzeuge, opencode-Version,
   KVM, Android-Umgebung, Prüfdateien, Katalog, freier Platz.
2. Dashboard → „Umgebung“ — dieselben Prüfungen plus Releasekennung
   (Version, Commit, Herkunft).
3. `curl -s http://127.0.0.1:8787/api/health` — App, Instanz-ID, Port,
   Version und Commit.
4. `vibe ui stop` und erneut starten, wenn die Oberfläche nicht antwortet.
5. Logs unter `$VIBE/_logs` prüfen; Token nicht in Tickets oder Chat kopieren.

| Symptom | Wahrscheinliche Ursache | Vorgehen |
| --- | --- | --- |
| „Port belegt, aber kein eigenes Dashboard erkannt“ | fremder Dienst auf dem Port | Port in `~/.config/vibe/config.json` ändern oder fremden Dienst beenden |
| Browser zeigt „Token fehlt oder falsch“ | alte URL oder Token neu erzeugt | `vibe ui` erneut starten und neue URL verwenden |
| `ModuleNotFoundError` nach Update | unvollständige Installation | `python3 scripts/setup-vibe.py --yes --update …`; V-021 prüft die Modulliste |
| Agentenlauf startet nicht | `tmux`/`flock` fehlt oder opencode nicht erreichbar | `vibe doctor`, `vibe server status` |
| opencode „nicht geprüft“ | installierte Version weicht von 2.1.4 ab | `docs/compatibility.md` befolgen; keine erzwungenen Schreibvorgänge |
| Prüfung meldet fehlenden Befehl | `.vibe/project.env` ohne `VERIFY_QUICK`/`VERIFY_FULL` | Projekt vorbereiten oder Werte ergänzen |
| Schreibfehler auf FUSE/NTFS | Unix-Rechte und Atomarität nicht zusicherbar | lokale Platte für Laufzeitdaten verwenden; Grenzen beachten |
| Dashboard beendet, Lauf läuft weiter | beabsichtigtes Verhalten | Lauf separat mit `vibe stop` beenden |
| Update meldet laufende Agenten, obwohl keiner läuft | verwaister Registereintrag ohne tmux-Sitzung oder laufendes Dashboard | `vibe runs` prüfen, `vibe runs prune`, bei Bedarf `vibe ui stop`, dann Update erneut |

## Sicherungen

- Agenten- und Konfigurationssicherungen: `vibe agent backups`,
  `vibe agent restore <name> <sicherung>`, `vibe mcp backups`,
  `vibe mcp restore`.
- Installationssicherungen: `_toolchain/backup-<Zeitstempel>/`, Rollback über
  `setup-vibe.py --rollback`.
- Sicherungen können sensible Daten enthalten. Sie gehören nicht in Git und
  nicht in eine Release.

## Self-Development

Die produktive Installation nicht während eines Agentenlaufs überschreiben.
Änderungen zuerst im Repository oder im Dev-Profil (`VIBE_PROFILE=dev`,
Port 8788) prüfen. Vor einem Update den Lauf beenden oder die dokumentierte
Sperre bewusst mit `--force` aufheben.

## Prüfungen und Nachweise

```
bash scripts/verify.sh quick
bash scripts/verify.sh full
```

`quick` prüft Manifest, Syntax und Geheimnisse. `full` führt zusätzlich die
Unit- und Browsertests aus und verlangt eine tatsächliche Testanzahl. Die
Prüfumgebung verwendet temporäre HOME-/VIBE-Verzeichnisse und eigene Ports.
In Umgebungen mit geerbtem `SANDBOX`/`VIBE_*` sowie schreibgeschütztem `/tmp`
muss der Lauf in einem Mount-Namespace erfolgen; das konkrete Verfahren und
die Ergebnisse stehen in `docs/checkliste.md`.

## Verwandte Dokumente

- `docs/handbuch.md` — Bedienung.
- `docs/grenzen.md` — bekannte Grenzen.
- `docs/checkliste.md` — Abnahmecheckliste mit Versionen und Ergebnissen.
- `docs/abnahme-bazzite.md` — manuelle Bazzite-Prüfung.
- `docs/compatibility.md` — opencode-Kompatibilität.
- `docs/features/V-018.md` — Installationslebenszyklus.
- `docs/features/V-020.md` — dieses Arbeitspaket.
