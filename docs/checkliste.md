# Abnahmecheckliste

Stand: 2026-11-03
Gilt für: vibe 0.18.0 (Repositorystand, siehe `VERSION`)
Bezug: V-020 (Browserabnahme, Dokumentation und Releasebasis)

Diese Checkliste hält Voraussetzungen, Prüfbefehle, tatsächliche Ergebnisse und
die manuellen Nachweise fest. Sie ist kein Ersatz für die automatisierten
Tests; sie belegt, was in welcher Umgebung wirklich ausgeführt wurde.

## 1. Voraussetzungen

| Komponente | Stand |
| --- | --- |
| Host | Bazzite 44.20261026.0 (Kinoite) |
| Host-Kernel | 7.2.11-ogc4.1.fc44.x86_64 |
| Steuerungscontainer | Fedora Linux 44 (Toolbx) |
| podman | 5.8.9 |
| distrobox | 1.8.2.5 |
| Python | 3.14.8 |
| tmux | 3.8 |
| flock | util-linux 2.41.5 |
| opencode | 2.2.5 installiert; geprüft ist 2.1.4 (`docs/compatibility.md`) |
| Playwright | 1.63.0 |
| Chromium | Google Chrome for Testing 153.0.8010.12 |
| desktop-file-validate | 0.28 |

## 2. Automatisierte Prüfungen

Die verbindlichen Befehle stehen in `.vibe/project.env`:

```
bash scripts/verify.sh quick
bash scripts/verify.sh full
```

`quick` prüft Importmanifest, Syntax und Geheimnisse. `full` führt zusätzlich
alle Unit- und Browsertests aus und verlangt eine tatsächliche Testanzahl.
`package` ist die Paketprüfung (`VERIFY_QUICK` plus optionaler Testnachweis bei
`VERIFY_PACKAGE_TESTS`). Die Engine liest `VERIFY_PACKAGE`/`VERIFY_FULL` nicht
mehr als Befehl; die autoritative `.vibe/project.env` trägt dafür die
Wrapperverschaltung (`VERIFY_PACKAGE="bash scripts/verify.sh package"`,
`VERIFY_FULL="bash scripts/verify.sh full"`, `VERIFY_ENV=<Label>`). Details in
`docs/features/AP7-Korbat.md`.

In der Agentenumgebung sind `SANDBOX`, `SANDBOX_TOOLS` und `VIBE_*` gesetzt und
`/tmp` ist ein eingeschränkter, nicht frei beschreibbarer Bereich. Die
vollständige Prüfung lief deshalb mit leerer Umgebung in einem
bubblewrap-Namespace mit schreibbarem `tmpfs` auf `/tmp` und dem Arbeitsbaum
unter `/tmp/work`:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$HOME" TERM=xterm \
  bwrap --dev-bind / / --tmpfs /tmp --dir /tmp/work \
  --bind /tmp/opencode/vibe-v020 /tmp/work \
  bash -c 'cd /tmp/work && bash scripts/verify.sh full'
```

Ein Lauf ohne diese Isolation scheitert erwartbar an `/tmp/vibe-next.lock`
(„Das Dateisystem ist nur lesbar“) und an geerbten `SANDBOX`-Werten; das ist
eine Grenze der Prüfumgebung, kein Testfehler des Projekts.

Ergebnis (ein repräsentativer vollständiger Lauf; die Sekundenangaben
schwanken je nach Maschine und Lauf):

```
Ran 856 tests in 106.579s
Ran 58 tests in 45.592s
OK: Tests erkannt: 914 (Minimum 1).
OK: Prüfung 'full' erfolgreich. (Exit 0)
```

Ausgangsstand vor diesem Arbeitspaket: 842 Unit- und 56 Browsertests
(898 erkannt). Die Differenz sind 14 neue Unit- und 2 neue Browsertests.

### Einzelne Prüfungen dieses Arbeitspakets

```
python3 -m unittest tests.unit.test_release -v
  Ran 14 tests
  OK

PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
  python3 -m unittest tests.browser.test_central_workflows_ui -v
  Ran 2 tests
  OK
```

Die Browserprüfung braucht `PLAYWRIGHT_BROWSERS_PATH`, weil die Prüfumgebung
`XDG_CACHE_HOME` in ein leeres temporäres Verzeichnis setzt.

## 3. Browserabnahme

`tests/browser/test_central_workflows_ui.py` startet das echte Dashboard
(`bin/vibe-web.py`) mit einem temporären `VIBE`-Ordner auf einem freien Port
und bedient es mit Chromium über Playwright.

| Test | Geprüfter Ablauf |
| --- | --- |
| `test_central_flow_lists_opens_creates_and_verifies` | Projektliste (Name, Typ, offene Zahl 2) → Projektdetail → Register „Arbeit“/„Ausgabe“ → Arbeitspaket `V-901` anlegen → Persistenz in `TICKETS.md` → `quick`-Prüfung starten → Ausgabe mit Prüftext → zurück zur Liste → offene Zahl 3 |
| `test_environment_view_shows_release_and_diagnosis` | Ansicht „Umgebung“ → Releasekarte mit `Version 0.18.0` und `Commit abcdef1` → Umgebungsprüfung mit echtem OK-/FEHL-Zustand |

Die Tests verwenden keine Attrappen der Fachlogik. Temporär sind nur Pfade,
Port und Browserinstanz.

## 4. Manuelle Bazzite-Prüfung

Die Host-Abnahme des Starters lief am 2026-11-02 mit dem Testcontainer
`vibe-v017-accept`, Dev-Profil, Port 8788 und einem Arbeitsbereich mit
Leerzeichen, Umlaut, `$`, Apostroph und Klammern. Alle acht Fälle endeten ohne
Fehler; das Rohprotokoll liegt unter `docs/features/V-017-bazzite.txt`
(„ERGEBNIS: 0 Fehler“).

Am 2026-11-03 wurden schreibgeschützt nachgeprüft:

| Prüfung | Ergebnis |
| --- | --- |
| Produktives Dashboard `GET /api/health` | HTTP 200, `ok: true`, Instanz `6a6dac450d2ae7bc`, Port 8787 |
| `python3 scripts/vibe_starter.py status` | `vibe läuft: http://127.0.0.1:8787/`, Exit 0 |
| `desktop-file-validate ~/.local/share/applications/vibe.desktop` | Exit 0 |

Details, Umgebung und Einschränkungen: `docs/abnahme-bazzite.md`.

## 5. Releaseprüfung

Eine Release wird ausschließlich aus versionierten Dateien eines Git-Stands
gebaut:

```
python3 scripts/build-release.py --source . --output dist
python3 scripts/build-release.py verify dist/vibe-<version>-<commit>.tar.gz
```

Geprüft werden:

- Byte-Gleichheit zweier Baue desselben Commits,
- Ausschluss unversionierter Laufzeitdaten (`web.token`, `_logs`, `_toolchain`,
  Sicherungen, `_secrets.env`),
- Aufnahme der versionierten Dateien einschließlich
  `docs/baseline-installation.sha256`,
- Ablehnung eines versionierten persönlichen Home-Pfads ohne Archivdatei,
- Ablehnung eines versionierten symbolischen Links statt stiller Umwandlung in
  eine reguläre Datei,
- Ablehnung eines manipulierten Archivs durch `verify`,
- fehlendes `RELEASE.json` und fehlende Pflichtdateien als Fehler.

Das konkrete Archiv des Arbeitspaket-Commits und seine SHA-256-Prüfsumme
stehen im Nachweis zu V-020 in `TICKETS.md`.

## 6. Dokumentation

| Dokument | Inhalt |
| --- | --- |
| `docs/handbuch.md` | Bedienung von Oberfläche und CLI |
| `docs/betrieb.md` | Pfade, Profile, Prozesse, Ports, Sicherungen, Installation, Release, Diagnose |
| `docs/grenzen.md` | veröffentlichte Grenzen und nicht zugesagte Funktionen |
| `docs/abnahme-bazzite.md` | manuelle Host-Abnahme und Nachprüfung |
| `docs/checkliste.md` | diese Checkliste |
| `docs/features/V-020.md` | fachliche und technische Dokumentation |
| `docs/trilium-index.md` | Zuordnung der Trilium-Notizen |

Die Trilium-Notiz zu V-020 wird unter „Features“ angelegt und nach dem
Schreiben gegengelesen; die ID steht in `docs/trilium-index.md`.

## 7. Bekannte Grenzen

- Browserabnahme nur mit Chromium 153; Firefox, WebKit und mobile Browser sind
  nicht automatisiert geprüft.
- Die manuelle Bazzite-Abnahme vom 2026-11-02 wurde nicht wiederholt.
- Die Releaseprüfung ist eine Heuristik für offensichtliche Geheimnisse und
  absolute Home-Pfade, kein vollständiges Secret-Scanning.
- V-012 (transaktionale Modellprofile) ist offen und in `docs/grenzen.md`
  veröffentlicht.

Die vollständige Liste steht in `docs/grenzen.md`.
