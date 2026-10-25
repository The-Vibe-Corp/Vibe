# Baseline — unveränderter Bestand (V-001)

Stand: 2026-10-25
Ausgangscommit: `2c4a621` (`init: vibe-Vorlage`)
Arbeitsbranch: `feature/v-001-baseline`
Bezug: `SPEC.md` (Abschnitt „Ausgangsstand und Nachweisstatus“), `TICKETS.md` V-001

Diese Bestandsaufnahme dokumentiert den übernommenen Stand, seine externen
Abhängigkeiten und den **tatsächlichen** Prüfstatus jeder Funktion. Sie ist
keine Freigabe: Ein Eintrag „vorhanden, noch nicht geprüft“ bedeutet, dass die
Funktion im Code existiert, aber in V-001 nicht ausgeführt oder getestet wurde.

Statuswerte (aus `SPEC.md`):

- `vorhanden und automatisiert geprüft`
- `vorhanden und manuell geprüft`
- `vorhanden, noch nicht geprüft`
- `teilweise vorhanden`
- `fehlt`

## 1. Import und Manifest

Der Programmstand wurde aus der funktionierenden lokalen Installation
übernommen. Zwei Dateien unterscheiden sich inhaltlich von der aktuell aktiven
Installation: Die aktive Fassung lädt lokale Geheimnis-Hooks und startet den
opencode-Server mit `opencode serve` statt `opencode web` (Abschnitt 3). Ein
Importmanifest existierte vor V-001 **nicht**
(`grep -rn "manifest"` fand nur Verweise in `README.md`, `SPEC.md` und
`TICKETS.md`). Es wurde in diesem Arbeitspaket erstellt:

- Manifest: `docs/import-manifest.json` (22 Dateien: `install-vibe.sh`,
  `bin/vibe`, `bin/vibe-run.sh`, `bin/vibe-web.py`, `bin/vibe_mcp.py`,
  `data/models.json` und 16 Vorlagendateien unter `templates/`).
- Prüfer: `scripts/check-import-manifest.py`.
- Regel: Änderungen an einer gelisteten Programmdatei sind nur zulässig, wenn
  der Manifesteintrag im selben Arbeitspaket aktualisiert und begründet wird.
  Laufzeitdaten, Sicherungen und Geheimnisse sind nicht Bestandteil des
  Manifests.

Reproduzierbare Prüfung:

```
$ python3 scripts/check-import-manifest.py
OK: 22 Dateien stimmen mit docs/import-manifest.json überein.
$ echo $?
0
```

Der Prüfer erkennt geänderte, fehlende und nicht gelistete Dateien sowie
Pfade außerhalb der Manifest-Bereiche; die Fehlerfälle sind in
`tests/unit/test_import_manifest.py` mit Fixtures abgedeckt.

## 2. Aktive Installation unverändert

Zu Beginn der Arbeiten wurde mit dem in diesem Paket neu erstellten Prüfskript
ein SHA-256-Snapshot der aktiven Installation angelegt
(`docs/baseline-installation.sha256`, 30 Dateien aus `bin/`, `templates/`,
`models.json`, `profiles.json`, `vibe.svg`, `verify/`). Er wurde vor jeglichem
Schreibzugriff auf die aktive Installation erstellt; es gab keinen solchen
Zugriff. `__pycache__`, Laufzeitdaten und die nicht programmatischen Bereiche
`gradle/`, `android-sdk/`, `config-backups/`, `agent-backups/` sind nicht im
Prüfumfang. Erstellt mit:

```
$ python3 scripts/active-install.py snapshot
OK: 30 Dateien der aktiven Installation in .../docs/baseline-installation.sha256 erfasst.
```

Nach Abschluss der Arbeiten geprüft mit:

```
$ python3 scripts/active-install.py verify
OK: aktive Installation unverändert (30 Dateien geprüft).
```

Es wurden keine Dateien unter `$VIBE/_toolchain` geändert, insbesondere nicht
unter `$VIBE/_toolchain/verify`. Die aktive Installation enthält bewusst
mehr Dateien als der Import; siehe Abschnitt 3.

## 3. Unterschiede zwischen Import und aktiver Installation

| Datei | Import (SHA-256, gekürzt) | Aktiv (SHA-256, gekürzt) | Ursache |
| --- | --- | --- | --- |
| `bin/vibe` | `5205ec8d2b96` | `01e4d3589f77` | Aktiv werden vor Server-/Dashboard-Start lokale Geheimnisse geladen (`vibe-secrets.sh`) und der opencode-Server mit `opencode serve --hostname 127.0.0.1 --port 4096` statt `opencode web --port 4096 --hostname 127.0.0.1` gestartet; der Import enthält beides nicht. Der Serverstart ist Gegenstand von V-007. |
| `bin/vibe-run.sh` | `deca3a9f6fc5` | `9fd033ebeadb` | Aktiv werden `vibe-secrets.sh` und `$VIBE/_secrets.env` vor dem Agentenlauf geladen; der Import enthält diese Anpassung nicht. |
| `bin/vibe-web.py`, `bin/vibe_mcp.py` | identisch | identisch | unverändert übernommen |
| `data/models.json` | `3f4842520afd` | `3f4842520afd` (`models.json` im Installationswurzelverzeichnis) | Inhalt identisch, anderer Ablageort; `install-vibe.sh` kopiert die Datei nach `$VIBE/_toolchain/models.json`. |

Nur in der aktiven Installation, **nicht** importiert (Laufzeit-/Geheimnisnähe):

- `bin/vibe-secrets.sh`, `bin/vibe-server-debug.sh`, `bin/vibe-launcher.sh`
- `bin/fritz-reconnect.py` (optionale Altintegration; laut `SPEC.md` standardmäßig
  zu deaktivieren)
- `vibe.svg`, `profiles.json`
- `config-backups/`, `agent-backups/`, `__pycache__/`
- `$VIBE/_secrets.env` (Geheimnisse, niemals ins Repository)

## 4. Externe Abhängigkeiten

Erhoben aus den Importen (`os`, `sys`, `re`, `json`, `subprocess`, `shutil`,
`time`, `tempfile`, `secrets`, `threading`, `queue`, `urllib`,
`http.server`) und den aufgerufenen Programmen. Es wird ausschließlich die
Python-Standardbibliothek verwendet; es gibt keine `requirements.txt`, kein
`package.json` und keinen Build im Repository.

| Abhängigkeit | Benötigt von | Geprüft in V-001 | Status |
| --- | --- | --- | --- |
| Python 3 (nur Standardbibliothek) | `bin/vibe`, `bin/vibe-web.py`, `bin/vibe_mcp.py`, Prüfskripte | `python3 --version` → 3.14.8; Syntaxprüfung | vorhanden |
| Bash | `install-vibe.sh`, `bin/vibe-run.sh`, Vorlagenskripte | `bash --version`; `bash -n` | vorhanden |
| Git | Projektliste, Status, Nachweise, Manifestprüfung | `git --version` → 2.56.0 | vorhanden |
| tmux | Agentenläufe, Dashboard, opencode-Server | `tmux -V` → 3.8 | vorhanden |
| flock (util-linux) | `bin/vibe-run.sh` (Durchgangssperre) | `command -v flock` | vorhanden |
| curl | Health-Checks (`server_health`) | `command -v curl` | vorhanden |
| opencode CLI | Modelllisting, Agentenläufe, Serverstart | `opencode --version` → 2.1.4 | vorhanden, Version nicht gegen Adapter geprüft (V-007) |
| distrobox | Wiedereintritt in den Container (`main()`) | im Container nicht installiert | fehlt im Container; Start erfolgt derzeit direkt |
| Android CLI, adb, emulator, Java | Android-Vorlage, `vibe emu` | `doctor` meldet OK | vorhanden |
| npm/npx | Web-Vorlage, MCP-Server (z. B. Trilium) | nicht in V-001 ausgeführt | vorhanden, nicht geprüft |
| Docker | Docker-Vorlage | nicht in V-001 ausgeführt | nicht geprüft |
| Netzwerk Loopback | Dashboard 8787, opencode 4096, MCP-Tests | nicht in V-001 gestartet | nicht geprüft |
| `~/.config/opencode/` | Agenten, opencode-Konfiguration | gelesen (nur lesend) | vorhanden |

Keine echten Modellaufrufe: `vibe models` liest mit `opencode models` nur den
Modellkatalog; es wurde keine Inferenzanfrage gesendet. MCP-Tests und
Agentenläufe wurden nicht ausgeführt.

## 5. CLI-Kommandos

Aufruf über `bin/vibe` (Tabelle in `bin/vibe:641-665`). „Beleg“ nennt die
Codestelle und die in dieser Sitzung tatsächlich beobachtete Prüfung.

| Typ | Funktion | Status | Beleg |
| --- | --- | --- | --- |
| CLI | `vibe list` | vorhanden und manuell geprüft | `bin/vibe:197-205`; in V-001 ausgeführt, Exit 0, Projektliste plausibel |
| CLI | `vibe status` | vorhanden und manuell geprüft | `bin/vibe:207-218`; `status vibe` ausgeführt, Exit 0, offene Punkte und Git-Status plausibel |
| CLI | `vibe run` | vorhanden, noch nicht geprüft | `bin/vibe:220-229`; startet tmux/opencode, in V-001 bewusst nicht ausgeführt |
| CLI | `vibe attach` | vorhanden, noch nicht geprüft | `bin/vibe:231-233`; interaktive tmux-Anhängung, nicht ausgeführt |
| CLI | `vibe logs` | vorhanden, noch nicht geprüft | `bin/vibe:235-239`; blockierendes `tail -f`, nicht ausgeführt |
| CLI | `vibe stop` | vorhanden, noch nicht geprüft | `bin/vibe:241-242`; beendet tmux-Sitzung, nicht ausgeführt |
| CLI | `vibe verify` | teilweise vorhanden | `bin/vibe:244-255`; Fehlerfall ohne Prüfbefehl ausgeführt (Exit 1); Rückgabecode des Prüfbefehls wird nicht weitergereicht |
| CLI | `vibe feedback` | vorhanden, noch nicht geprüft | `bin/vibe:257-274`; interaktiver Schreibvorgang, nicht ausgeführt |
| CLI | `vibe new` | vorhanden, noch nicht geprüft | `bin/vibe:308-327`; legt Projekt und Git-Repo an, nicht ausgeführt |
| CLI | `vibe init` | vorhanden, noch nicht geprüft | `bin/vibe:300-306`; schreibt Vorlagen, nicht ausgeführt |
| CLI | `vibe roots` | vorhanden und manuell geprüft | `bin/vibe:135-151`; ausgeführt, Exit 0, ein Entwicklungsordner mit 7 Projekten |
| CLI | `vibe scan` | vorhanden und manuell geprüft | `bin/vibe:653`; Alias auf `cmd_roots()`, ausgeführt, Exit 0 |
| CLI | `vibe agents` | vorhanden und manuell geprüft | `bin/vibe:349-364,428-435`; ausgeführt, Exit 0, globale Agenten plausibel |
| CLI | `vibe agent` | vorhanden, noch nicht geprüft | `bin/vibe:441-457`; `new/edit/show/rm`, Editor und Schreibzugriff nicht ausgeführt |
| CLI | `vibe models` | vorhanden und manuell geprüft | `bin/vibe:459-466`; ausgeführt, Exit 0; Daten aus `data/models.json` bleiben ungeprüfte Altdaten (V-011) |
| CLI | `vibe model` | vorhanden, noch nicht geprüft | `bin/vibe:468-477`; schreibt Agentendatei, nicht ausgeführt |
| CLI | `vibe profile` | teilweise vorhanden | `bin/vibe:515-528`; Liste ausgeführt, Exit 0; `use` schreibt Agenten und wurde nicht ausgeführt (V-012) |
| CLI | `vibe mcp` | teilweise vorhanden | `bin/vibe:584-586`, `bin/vibe_mcp.py:335-358`; `list` ausgeführt (Exit 0), `show/test/on/off/rm` nicht geprüft; Transport-/Limitgrenzen fehlen (V-013/V-014) |
| CLI | `vibe emu` | vorhanden, noch nicht geprüft | `bin/vibe:531-534`; startet Emulator, nicht ausgeführt |
| CLI | `vibe ui` | vorhanden, noch nicht geprüft | `bin/vibe:550-560`; startet Dashboard in tmux, nicht ausgeführt |
| CLI | `vibe server` | vorhanden, noch nicht geprüft | `bin/vibe:540-548`; opencode-Prozessverwaltung, nicht ausgeführt |
| CLI | `vibe types` | vorhanden und manuell geprüft | `bin/vibe:277-285`; ausgeführt, Exit 0, fünf Typen plus `common` |
| CLI | `vibe doctor` | vorhanden und manuell geprüft | `bin/vibe:562-582`; ausgeführt, Exit 0, Umgebungsprüfungen plausibel |
| CLI | `vibe` (ohne Argument) | vorhanden, noch nicht geprüft | `bin/vibe:609-639`; interaktives Menü, nicht ausgeführt |
| CLI | `vibe <unbekannt>` | vorhanden und manuell geprüft | `bin/vibe:661-662`; ausgeführt, Exit 0, gibt die Aufrufhilfe aus |

## 6. HTTP-API-Routen

Alle Routen liegen in `bin/vibe-web.py`. Der Server bindet nur an
`127.0.0.1` (`bin/vibe-web.py:414`). Authentisierung: `_ok()` prüft den
`Host`-Header und vergleicht das Token; das Token wird als `X-Token` oder als
Query-Parameter `t` akzeptiert (`bin/vibe-web.py:88-92`). In V-001 wurde
**kein** Webserver gestartet (es läuft bereits eine produktive Instanz); alle
API-Funktionen sind daher „noch nicht geprüft“. Die Einstufung „teilweise
vorhanden“ nennt bereits sichtbare Lücken, die in V-004 zu beheben sind.

| Typ | Funktion | Status | Beleg |
| --- | --- | --- | --- |
| API | `GET /` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:95`; liefert die eingebettete Seite, nicht ausgeführt |
| API | `GET /api/projects` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:98`; nicht ausgeführt |
| API | `GET /api/project` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:99`; nicht ausgeführt |
| API | `GET /api/roots` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:100`; nicht ausgeführt |
| API | `GET /api/agents` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:101`; nicht ausgeführt |
| API | `GET /api/agent` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:102-103`; nicht ausgeführt |
| API | `GET /api/mcp` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:104`; nicht ausgeführt |
| API | `GET /api/mcp_entry` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:105-106`; nicht ausgeführt |
| API | `GET /api/types` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:107`; nicht ausgeführt |
| API | `GET /api/doctor` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:108`; nicht ausgeführt |
| API | `GET /api/server` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:109`; nicht ausgeführt |
| API | `GET /api/stream` | teilweise vorhanden | `bin/vibe-web.py:110,188-207`; Token im Query-String möglich, keine Origin-Prüfung; nicht ausgeführt |
| API | `POST /api/run` | teilweise vorhanden | `bin/vibe-web.py:124`; Token/Host geprüft, aber keine Origin-/CSRF-/Größenprüfung (V-004); nicht ausgeführt |
| API | `POST /api/stop` | teilweise vorhanden | `bin/vibe-web.py:125`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/verify` | teilweise vorhanden | `bin/vibe-web.py:126`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/init` | teilweise vorhanden | `bin/vibe-web.py:127`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/feedback` | teilweise vorhanden | `bin/vibe-web.py:128-130`; Auth-Lücke, ID-Vergabe nicht gegen Parallelzugriff gesichert (V-009) |
| API | `POST /api/new` | teilweise vorhanden | `bin/vibe-web.py:131`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/roots` | teilweise vorhanden | `bin/vibe-web.py:132-141`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/agent_template` | teilweise vorhanden | `bin/vibe-web.py:142-143`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/agent` | teilweise vorhanden | `bin/vibe-web.py:144-152`; Auth-Lücke, Schreibvorgang nicht atomar (V-005) |
| API | `POST /api/mcp` | teilweise vorhanden | `bin/vibe-web.py:153-162`; Auth-Lücke, JSONC-Verlustgrenzen (V-013) |
| API | `POST /api/profiles` | teilweise vorhanden | `bin/vibe-web.py:163-175`; Auth-Lücke, Anwendung nicht transaktional (V-012) |
| API | `POST /api/model` | teilweise vorhanden | `bin/vibe-web.py:176`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/server` | teilweise vorhanden | `bin/vibe-web.py:177`; Auth-Lücke wie `/api/run`; nicht ausgeführt |
| API | `POST /api/shutdown` | teilweise vorhanden | `bin/vibe-web.py:178-180`; Auth-Lücke wie `/api/run`; nicht ausgeführt |

## 7. UI-Funktionen

Die Oberfläche ist eine eingebettete HTML/JS-Seite (`bin/vibe-web.py:209-410`).
In V-001 wurde sie nicht im Browser geöffnet; alle Einträge sind daher
„vorhanden, noch nicht geprüft“.

| Typ | Funktion | Status | Beleg |
| --- | --- | --- | --- |
| UI | `Tab Projekte` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:237-291`; Projektliste, Detail, Roots, Neuanlage; kein Browsertest |
| UI | `Tab Agenten & Modelle` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:292-358`; Agentenliste, Formular, Roh-Editor, Profile; kein Browsertest |
| UI | `Tab MCP-Tools` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:360-406`; Liste, Formular, Test, Aktivierung; kein Browsertest |
| UI | `Tab Umgebung` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:407-408`; Doctor-Anzeige; kein Browsertest |
| UI | `Kopfzeile opencode Start/Stop` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:242-245`; ruft `POST /api/server`; kein Browsertest |
| UI | `Kopfzeile Dashboard beenden` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:244`; ruft `POST /api/shutdown`; kein Browsertest |
| UI | `Log-Stream` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:282-291`; EventSource auf `/api/stream`; kein Browsertest |

## 8. Funktionsbereiche aus SPEC.md

| Bereich | Status | Bewertung |
| --- | --- | --- |
| Projekte und Entwicklungsordner | teilweise vorhanden | Einlesen, Liste, Detail, Roots vorhanden; gleichnamige Projekte werden nur als `name@root` unterschieden, URLs/IDs sind nicht kollisionsfrei (V-008) |
| Projektvorlagen | teilweise vorhanden | Fünf Typen plus `common` vorhanden; unbekannter Typ fällt still auf `generic` zurück; Android-Prüfung ist nicht global (V-008) |
| Arbeitspakete und Feedback | teilweise vorhanden | Kommentare werden ignoriert, `BLOCKIERT` bleibt offen; Nachweisprüfung vorhanden; ID-Vergabe ohne Sperre (V-009) |
| Agenten | teilweise vorhanden | Liste, Anlegen, Bearbeiten, Kopieren, Löschen, Sicherung vorhanden; Wiederherstellung, atomare Writes und verlustfreie Feldpflege fehlen (V-005/V-010) |
| Modelle und Anbieter | teilweise vorhanden | Modelllisting über opencode, Katalogdatei; Altdaten ohne Quellen-/Datumsnachweis, keine Anbieter-Trennung (V-011) |
| Modelltabelle | teilweise vorhanden | Tabelle und Detailfelder in `data/models.json`/UI vorhanden; unbekannte Werte, Quellen, Preiseinheiten nicht durchgängig belegt (V-011) |
| Modellprofile | teilweise vorhanden | Profile vorhanden; keine Änderungsvorschau, keine Transaktion, kein Rollback, leeres Profil wird nicht als Fehler behandelt (V-012) |
| MCP-Verwaltung | teilweise vorhanden | list/show/save/delete/toggle, JSONC-Schreiben, Maskierung vorhanden; Kommentare innerhalb des MCP-Blocks und Formatierung gehen verloren (V-013) |
| MCP-Tests | teilweise vorhanden | initialize/tools/list, lokale und Remote-Transporte, Limits im Code; keine explizite Transportauskunft, kein vollständiges Prozess-Cleanup belegt (V-014) |
| Agentenläufe und Prüfungen | teilweise vorhanden | Start/Stop/Logs über tmux; keine eindeutigen Lauf-IDs, Exitcode wird nicht weitergereicht, Prüfadapter projekttypspezifisch (V-015) |
| App und opencode beenden | teilweise vorhanden | Getrennte Aktionen vorhanden; tmux-Sitzungsnamen statt verwalteter Prozessliste, kein Nachweis gegen fremde Prozesse (V-016) |
| Bazzite-Startmenü | fehlt | Kein Desktopstarter, kein Icon, kein Installer im Repository (V-017) |
| Diagnose | teilweise vorhanden | `vibe doctor` prüft Werkzeuge, Pfade, Prüfsummen; opencode-Version und unterstützte Funktionen werden nicht ermittelt (V-007) |
| Installation/Aktualisierung/Rollback | fehlt | Nur `install-vibe.sh` (kopiert Dateien); keine Versionierung, Sicherung oder Rollback (V-018) |
| Webserver-Sicherheit | teilweise vorhanden | Loopback-Bindung und Token vorhanden; Origin-/CSRF-Prüfung, Requestlimits, strukturierte Fehler fehlen (V-004) |
| Automatisierte Tests | fehlt (vor V-001) | Vor diesem Paket existierten im Repository keine Tests; V-001 ergänzt nur Prüfungen für den Importbestand, keine App-Tests |

## 9. Sicherheitsbefunde (nur erfasst, nicht behoben)

Diese Befunde sind bewusst **nicht** in V-001 korrigiert; sie gehören zu den
genannten Folgepaketen.

1. `sh()` und mehrere Aufrufe verwenden `shell=True` bzw. Shell-Strings
   (`bin/vibe:50-55,226-227,317,323,534,543,555`). → V-003.
2. `cmd_verify` startet die Prüfung, gibt deren Exitcode aber nicht zurück
   (`bin/vibe:252-255`); `vibe verify` kann dadurch trotz fehlgeschlagener
   Prüfung mit 0 enden. → V-002/V-015.
3. Token wird zusätzlich als URL-Query-Parameter akzeptiert
   (`bin/vibe-web.py:91`); keine Origin-/CSRF-Prüfung, keine Begrenzung der
   Request-Größe (`bin/vibe-web.py:116-121`). → V-004.
4. Feedback-IDs werden als „höchste vorhandene + 1“ ohne Sperre vergeben
   (`bin/vibe:257-259`). → V-009.
5. Profilanwendung schreibt Agenten nacheinander ohne Transaktion
   (`bin/vibe:497-513`). → V-012.
6. Agenten-/Konfigurationssicherungen nutzen Sekunden-Zeitstempel und sind
   nicht kollisionsfrei (`bin/vibe:384-386`, `bin/vibe_mcp.py:124-127`). → V-005.
7. Der Import enthält keine Geheimnis-Injektion; die aktive Installation lädt
   `_secrets.env` über eigene Hooks. Diese Hooks sind nicht versioniert und
   müssen in V-006/V-018 sicher neu aufgebaut werden.

## 10. Geheimnisse

```
$ python3 scripts/check-no-secrets.py
OK: keine Geheimnisse erkannt.
$ echo $?
0
```

Der Scanner prüft typische Schlüsselformate (AWS, GitHub, OpenAI/Anthropic,
Slack, Google, private Schlüssel, Passwort-URLs, Zugangsdaten-Zuweisungen und
`.env`-Zeilen) und überspringt `.git`, `__pycache__` und Binärdateien. Dateien
über 2 MiB werden ebenfalls nicht eingelesen und daher nicht geprüft. Das ist
eine Heuristik, kein vollständiges Secret-Scanning. Zusätzlich gilt:

- `$VIBE/_secrets.env` und `bin/vibe-secrets.sh` liegen außerhalb des
  Repositories und wurden nicht importiert.
- `git log` enthält bisher nur den Initialcommit mit Platzhalterdateien.
- Eine `.gitignore` schützt künftig vor `__pycache__`, `.venv`, Logs und
  Token-Dateien.

## 11. Fehlende ursprüngliche Installer und Artefakte

Der übernommene Stand ist **nicht** aus einem vollständigen Installationspaket
reproduzierbar. Dokumentiert fehlen oder sind eingeschränkt:

| Artefakt | Verweis im Bestand | Folge |
| --- | --- | --- |
| `install.sh` / `install2.sh` | `bin/vibe:571` fordert „install.sh / install2.sh ausführen“; `~/.config/schreibfuchs-verify.sha` verweist auf `verify.sh` | Die Prüfsummen-Abnahme der Verify-Dateien ist nicht aus dem Repository reproduzierbar |
| `install-vibe.sh` (im Repository) | `install-vibe.sh:6` lehnt ein Kit unterhalb von `$VIBE/<projekt>` ab | Das Repository liegt unter `$VIBE/vibe`; ein Aufruf aus diesem Pfad wird abgelehnt. Eine Installation direkt aus dem Repository ist derzeit nicht möglich (V-018) |
| Uninstaller | `SPEC.md` (Installation/Rollback), V-018 | Deinstallation nicht möglich |
| Desktopdatei und Startmenü-Installer | `SPEC.md` (Bazzite-Startmenü), V-017 | Kein Start über das Anwendungsmenü |
| Icon `vibe.svg` | nur in der aktiven Installation | Startmenüeintrag ohne Icon |
| `vibe-launcher.sh` | nur in der aktiven Installation | Kein „läuft schon?“-Starter mit Browseröffnung |
| `vibe-secrets.sh`, `_secrets.env` | nur in der aktiven Installation | Geheimnisbereitstellung nicht reproduzierbar; absichtlich nicht importiert |
| `fritz-reconnect.py` | nur in der aktiven Installation; `bin/vibe-run.sh:12-13` | Optionale Altintegration fehlt im Quellstand und ist laut SPEC standardmäßig zu deaktivieren |
| `vibe-server-debug.sh` | nur in der aktiven Installation | Diagnosehilfe nicht versioniert |
| `profiles.json` (Laufzeitkopie) | nur in der aktiven Installation; wird sonst aus `DEFAULT_PROFILES` erzeugt | Kein reproduzierbarer Ausgangsstand für Profile |
| `scripts/verify.sh` (dieses Projekt) | `AGENTS.md`, `README.md`, V-002 | Projektprüfung noch nicht möglich; `.vibe/project.env` enthält `echo TODO` |
| Automatisierte Tests/CI | keine | Vor V-001 kein Regressionsschutz |

## 12. Reproduzierbare Prüfungen

Alle Prüfungen laufen lokal, ohne Netzverbindung und ohne Modellaufrufe.

```
$ python3 scripts/check-import-manifest.py
OK: 22 Dateien stimmen mit docs/import-manifest.json überein.

$ python3 scripts/check-syntax.py
OK: 12 Python-, 5 Bash- und 4 JSON-Datei(en) syntaktisch geprüft.

$ python3 scripts/check-no-secrets.py
OK: keine Geheimnisse erkannt.

$ python3 scripts/active-install.py verify
OK: aktive Installation unverändert (30 Dateien geprüft).

$ python3 -m unittest discover -s tests/unit -v
...
Ran 30 tests in 1.359s

OK
```

Hinweis: `check-syntax.py` prüft Python mit `compile()` und Bash mit
`bash -n`; es werden keine Projektprogramme gestartet. Die Tests unter
`tests/unit/` enthalten echte Zusicherungen und decken Erfolgs- und Fehlerfälle
ab.

## 13. Zusammenfassung des Prüfstatus

- Automatisiert geprüft: **keine** App-Funktion. Die automatisierten Tests
  betreffen ausschließlich den Importbestand (Manifest, Syntax, Geheimnisse,
  Installations-Snapshot, Inventar-Abdeckung).
- Manuell geprüft (read-only Smoke-Test in dieser Sitzung): `list`, `status`,
  `roots`, `scan`, `agents`, `models`, `profile` (Liste), `mcp list`, `types`,
  `doctor`, Aufrufhilfe sowie `verify __nicht_vorhanden__` als Fehlerfall
  (rc=1, „Projekt ... nicht gefunden“). Das interaktive Menü ohne TTY endet mit
  `EOFError`; es wurde nicht als Funktionstest gewertet. Befehle und
  Beobachtungen: `docs/features/V-001.md`, Abschnitt „Read-only Smoke-Tests“.
- Noch nicht geprüft: alle schreibenden, interaktiven, Prozess-startenden und
  Web-Funktionen.
- Teilweise vorhanden: siehe Abschnitte 5–8; die Lücken sind den Folgepaketen
  zugeordnet.
- Fehlt: Startmenüintegration, reproduzierbare Installation/Rollback,
  Projektprüfung und automatisierte App-Tests.

Damit ist V-001 eine ehrliche Ausgangsbasis: Der Bestand ist versioniert und
gegen Veränderung abgesichert, aber **keine** Funktion gilt als vollständig
abgenommen.

## 14. Dokumentation

- Fachliche und technische Dokumentation: `docs/features/V-001.md`.
- Trilium: `vibe` → `Features` → `V-001 Bestandsaufnahme und Absicherung`
  (Notiz-ID `eMU1JVlKt1n5`); Zuordnung in `docs/trilium-index.md`.
