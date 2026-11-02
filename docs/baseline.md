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
- `vibe.svg`, `profiles.json`
- `config-backups/`, `agent-backups/`, `__pycache__/`
- `$VIBE/_secrets.env` (Geheimnisse, niemals ins Repository)

`bin/fritz-reconnect.py` lag in V-001 nur in der aktiven Installation. Seit F5
liegt der Helfer im Repository (`bin/fritz-reconnect.py`), wird von
`install-vibe.sh` mitinstalliert und ist standardmäßig **nicht** aktiv: Die
Automatik ist aus, bis sie im Dashboard eingeschaltet wird.

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
| fritzconnection (optional) | `bin/fritz-reconnect.py` | nicht in V-001 ausgeführt; F5 prüft nur den Zustand und Attrappen | optional, nur für den Reconnect; Interpreter unter `$VIBE/_toolchain/fritz-venv` oder `~/.venvs/fritz`, sonst meldet das Dashboard „nicht bereit“ |
| opencode CLI | Modelllisting, Agentenläufe, Serverstart | `opencode --version` → 2.1.4 | vorhanden, Version nicht gegen Adapter geprüft (V-007) |
| distrobox | Wiedereintritt in den Container (`main()`) | im Container nicht installiert | fehlt im Container; Start erfolgt derzeit direkt |
| Android CLI, adb, emulator, Java | Android-Vorlage, `vibe emu` | `doctor` meldet OK | vorhanden |
| npm/npx | Web-Vorlage, MCP-Server (z. B. Trilium) | nicht in V-001 ausgeführt | vorhanden, nicht geprüft |
| Docker | Docker-Vorlage | nicht in V-001 ausgeführt | nicht geprüft |
| Netzwerk Loopback | Dashboard 8787, opencode 4096, MCP-Tests | nicht in V-001 gestartet | nicht geprüft |
| `~/.config/opencode/` | Agenten, opencode-Konfiguration | gelesen (nur lesend) | vorhanden |
| `fritzconnection` (optional, eigenes venv) + `~/.config/fritz.env` | `bin/fritz-reconnect.py` (F5) | nicht in V-001; F5 prüft nur mit Attrappen | optional; fehlend wird im Dashboard als „nicht bereit“ gemeldet |
| `scripts/setup-vibe.py` (F6) | Installation, Werkzeugprüfung, Wiederverwendung | `tests/unit/test_setup_vibe.py` (45 Tests) mit simulierten Plattformen und temporären Zielordnern | vorhanden und automatisiert geprüft (Linux/Container/Windows-Planung); kein echter Paketmanager- oder Windows-Lauf |
| `install-vibe.sh` (F6) | Kompatibler Linux-Einstieg | Wrapper-Test startet den echten Setup in temporärem `VIBE`/`HOME` | vorhanden und automatisiert geprüft |
| `setup-vibe.cmd` (F6) | Windows-Einstieg, bootstrappt Python über `winget` | nur statisch geprüft (Datei und Aufruf), kein Windows-Lauf | vorhanden, nicht auf Windows ausgeführt |
| npm (optional, F6) | Installation von `opencode` über `opencode-ai` | Aufrufplan im Test; `npm view opencode-ai name` in dieser Umgebung geprüft | vorhanden; nur mit Zustimmung ausgeführt |
| WSL2/Docker unter Windows (F6) | `tmux`/`flock` für Agentenläufe | nicht ausgeführt; Setup meldet die Grenze | fehlt nativ unter Windows; dokumentierte Voraussetzung |

Der Setup kopiert Programmdateien und Vorlagen, legt den Startbefehl an und
registriert vorhandene Git-Projekte. Laufzeitdaten (`vibe.json`,
`models.json`, `profiles.json`, `fritz.json`, `_logs`) und vorhandene
`.vibe/project.env` werden nicht überschrieben. `install-vibe.sh` beendet
anders als der frühere Stand keine laufende Dashboard-Sitzung mehr; ein
laufendes Dashboard wird erst beim nächsten Start auf den neuen Stand
zurückgreifen.


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
| CLI | `vibe pause` | vorhanden und automatisiert geprüft | `bin/vibe:404-448`; `tests/unit/test_pause_after_package.py` prüft Anfordern, Status, Aufheben und die Ablehnung unbekannter Projekte ohne Markierung; `bin/vibe-run.sh:31-65` verbraucht die Markierung und startet kein neues Paket |
| CLI | `vibe ask` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_ask`); `tests/unit/test_questions.py` prüft Stellen mit Auswahl, Projektableitung, Ablehnung unbekannter Projekte, Zeitlimit mit Exit-Code 3 und Fortsetzen mit `--wait`; `tests/browser/test_questions_ui.py` zeigt die Frage samt Vorschlägen im Dashboard |
| CLI | `vibe questions` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_questions`); `tests/unit/test_questions.py` prüft die Liste offener Fragen mit nummerierten Vorschlägen |
| CLI | `vibe answer` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_answer`); `tests/unit/test_questions.py` prüft Auswahl- und freie Antwort sowie die Quelle `--by agent`; `tests/unit/test_questions.py` und `tests/browser/test_questions_ui.py` prüfen die Ablehnung einer zweiten Antwort |
| CLI | `vibe autonomous` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_autonomous`); `tests/unit/test_questions.py` prüft Ein/Aus/Status je Projekt, die sofortige Entscheidung im aktiven Modus und den Abbruch eines laufenden Wartens beim Einschalten |
| CLI | `vibe fritz` | vorhanden und automatisiert geprüft | `bin/vibe:455-595`; `tests/unit/test_fritz_reconnect.py` prüft Automatik aus/an, Status ohne Zugangsdaten, manuellen Reconnect gegen eine Attrappe, Fehler, Timeout und die Automatiksperre des Läufers; `bin/vibe-run.sh:53-56` ruft den Wächter nach einem Agentenfehler auf |
| CLI | `vibe verify` | teilweise vorhanden | `bin/vibe:244-255`; Fehlerfall ohne Prüfbefehl ausgeführt (Exit 1); Rückgabecode des Prüfbefehls wird nicht weitergereicht |
| CLI | `vibe feedback` | vorhanden, noch nicht geprüft | `bin/vibe:257-274`; interaktiver Schreibvorgang, nicht ausgeführt |
| CLI | `vibe new` | vorhanden, noch nicht geprüft | `bin/vibe:308-327`; legt Projekt und Git-Repo an, nicht ausgeführt |
| CLI | `vibe init` | vorhanden, noch nicht geprüft | `bin/vibe:300-306`; schreibt Vorlagen, nicht ausgeführt |
| CLI | `vibe roots` | vorhanden und manuell geprüft | `bin/vibe:135-151`; ausgeführt, Exit 0, ein Entwicklungsordner mit 7 Projekten |
| CLI | `vibe scan` | vorhanden und manuell geprüft | `bin/vibe:653`; Alias auf `cmd_roots()`, ausgeführt, Exit 0 |
| CLI | `vibe agents` | vorhanden und manuell geprüft | `bin/vibe:349-364,428-435`; ausgeführt, Exit 0, globale Agenten plausibel |
| CLI | `vibe rights` | vorhanden und automatisiert geprüft | `bin/vibe:371-386`; `tests/unit/test_project_write_dirs.py` prüft Liste, Hinzufügen, Entfernen und Zurücksetzen ohne Schreibzugriff auf produktive Konfiguration |
| CLI | `vibe sandbox` | vorhanden und automatisiert geprüft | `bin/vibe:388-474`; `tests/unit/test_sandbox.py` prüft Status, Ein-/Ausschalten, Werkzeugliste, Ablehnung von Steuerzeichen, bubblewrap-Argumente, die `/tmp`-Grenze, die schreibgeschützte `.vibe`-Konfiguration und echte sandboxed Schreibversuche |
| CLI | `vibe agent` | vorhanden, noch nicht geprüft | `bin/vibe:441-457`; `new/edit/show/rm`, Editor und Schreibzugriff nicht ausgeführt |
| CLI | `vibe models` | vorhanden und manuell geprüft | `bin/vibe:459-466`; ausgeführt, Exit 0; Daten aus `data/models.json` bleiben ungeprüfte Altdaten (V-011) |
| CLI | `vibe model` | vorhanden, noch nicht geprüft | `bin/vibe:468-477`; schreibt Agentendatei, nicht ausgeführt |
| CLI | `vibe profile` | teilweise vorhanden | `bin/vibe:515-528`; Liste ausgeführt, Exit 0; `use` schreibt Agenten und wurde nicht ausgeführt (V-012) |
| CLI | `vibe costs` | vorhanden und automatisiert geprüft | `bin/vibe:1835-1873` (`cmd_costs`); `tests/unit/test_costs.py` prüft Übersicht, Paketzeilen, Summen, unbekannte Preise (0 €) und die Ausgabe in Euro; die opencode-Datenbank wird nur lesend gelesen |
| CLI | `vibe mcp` | teilweise vorhanden | `bin/vibe:584-586`, `bin/vibe_mcp.py:335-358`; `list` ausgeführt (Exit 0), `show/test/on/off/rm` nicht geprüft; Transport-/Limitgrenzen fehlen (V-013/V-014) |
| CLI | `vibe emu` | vorhanden, noch nicht geprüft | `bin/vibe:531-534`; startet Emulator, nicht ausgeführt |
| CLI | `vibe ui` | vorhanden, noch nicht geprüft | `bin/vibe:550-560`; startet Dashboard in tmux, nicht ausgeführt |
| CLI | `vibe server` | vorhanden, noch nicht geprüft | `bin/vibe:540-548`; opencode-Prozessverwaltung, nicht ausgeführt |
| CLI | `vibe types` | vorhanden und manuell geprüft | `bin/vibe:277-285`; ausgeführt, Exit 0, fünf Typen plus `common` |
| CLI | `vibe doctor` | vorhanden und manuell geprüft | `bin/vibe:562-582`; ausgeführt, Exit 0, Umgebungsprüfungen plausibel |
| CLI | `vibe paths` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_paths`), `bin/vibe_paths.py`; `tests/unit/test_vibe_paths.py` prüft JSON-Ausgabe, Dev-Profil mit eigenen Ports, persönliche Einstellungen, Pfade mit Leerzeichen, ungültige Ports und unbekannte Argumente; die Abfrage legt keine Verzeichnisse an |
| CLI | `vibe` (ohne Argument) | vorhanden, noch nicht geprüft | `bin/vibe:609-639`; interaktives Menü, nicht ausgeführt |
| CLI | `vibe <unbekannt>` | vorhanden und manuell geprüft | `bin/vibe:661-662`; ausgeführt, Exit 0, gibt die Aufrufhilfe aus |

## 6. HTTP-API-Routen

Alle Routen liegen in `bin/vibe-web.py`. Der Server bindet nur an Loopback
(`VIBE_UI_BIND`, Standard `127.0.0.1`; jede andere Adresse bricht den Start
ab). Seit V-004 prüft `_guard()` zentral den `Host`-Header (nur Loopback) und
bei Schreibzugriffen zusätzlich `Origin` und `Sec-Fetch-Site`. `_authorized()`
verlangt ein gültiges Token per `X-Token`; nur `/api/stream` akzeptiert
zusätzlich `t` im Query-String, weil EventSource keine Header setzen kann.
Zugriffslogs enthalten nur Methode und Pfad ohne Query-String. `POST` verlangt
`Content-Type: application/json`, eine `Content-Length` und höchstens 1 MiB;
Fehler sind strukturiert (`ok`, `error.code`, `error.message`).
`GET /api/health` ist ohne Token lesbar und nennt `app`, `instance`, `bind`,
`port`, `pid` und `started`, aber keine Geheimnisse. Transport, Health und
Requestlimits sind in `tests/unit/test_web_api_security.py` geprüft; die
fachlichen Routen darunter bleiben, soweit unten nicht anders belegt, ohne
eigenen Test.

| Typ | Funktion | Status | Beleg |
| --- | --- | --- | --- |
| API | `GET /` | vorhanden, noch nicht geprüft | `do_GET`; liefert die eingebettete Seite, kein eigener Test |
| API | `GET /api/health` | vorhanden und automatisiert geprüft | `_health()`; `tests/unit/test_web_api_security.py` prüft Identität (vibe, Instanz, Port, PID), Stabilität, fremden Host und dass weder Token noch Token-Wort in der Antwort stehen |
| API | `GET /api/projects` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/project` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/roots` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/agents` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/costs` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_costs.py` prüft Übersicht, Projektdetail, Tokenpflicht (403) und unbekanntes Projekt (404); `tests/browser/test_costs_ui.py` öffnet die Kostenansicht im Browser |
| API | `GET /api/agent` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/mcp` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/mcp_entry` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/types` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/doctor` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/fritz` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_fritz_reconnect.py` prüft Status, Tokenpflicht und dass das Passwort nicht in der Antwort steht |
| API | `GET /api/questions` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_questions.py` prüft offene Fragen mit Vorschlägen, leere Liste nach der Antwort und die Tokenpflicht (403) |
| API | `POST /api/questions` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_questions.py` prüft Auswahl- und freie Antwort, Rückgabe der neuen offenen Liste, Ablehnung ungültiger IDs/Auswahlen, unbekannter Aktionen und einer zweiten Antwort ohne Überschreiben |
| API | `GET /api/autonomous` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_questions.py` prüft den Zustand je Projekt, unbekannte Projekte (404) und die Tokenpflicht (403) |
| API | `POST /api/autonomous` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_questions.py` prüft Ein- und Ausschalten, die gespeicherte Datei, unbekannte Aktionen (400) und die Tokenpflicht (403) |
| API | `POST /api/fritz` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_fritz_reconnect.py` prüft Automatik an/aus, manuellen Reconnect, Fehlerfall, fehlende Konfiguration, unbekannte Aktion und Tokenpflicht |
| API | `GET /api/server` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/stream` | teilweise vorhanden | `stream()`; Token nur im Query-String (EventSource), Host geprüft; Origin nicht anwendbar; nicht ausgeführt |
| API | `POST /api/run` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/stop` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/pause` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_pause_after_package.py` prüft Anfordern, Aufheben, unbekannte Aktion und wahrheitsgemäße Meldung; `tests/unit/test_web_api_security.py` nutzt die Route für Token-, Host-, Origin-, JSON- und Größenprüfungen |
| API | `POST /api/verify` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/init` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/feedback` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_feedback_capture.py` prüft Anlegen mit Titel und Beschreibung, Ablehnung fehlender Titel und Tokenpflicht; `tests/unit/test_work_packages.py` prüft die Bugmeldung mit `kind: "bug"` und die Kennzeichnung in der Projektdetail-Antwort; ID-Vergabe mit Prüfsummenwiederholung (V-009) |
| API | `POST /api/ticket` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_work_packages.py` prüft Anlegen, Bearbeiten und Löschen von Arbeitspaketen, doppelte oder ungültige IDs, unbekannte IDs und Aktionen ohne Dateiänderung |
| API | `GET /api/guide` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_project_guide.py` prüft Schritte, Dateien, Entwürfe, Agentenzustand und die Tokenpflicht |
| API | `POST /api/guide` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_project_guide.py` prüft Speichern mit Dateianlage, Ablehnung unbekannter Schritte ohne Schreiben sowie Übernehmen und Verwerfen von Entwürfen |
| API | `POST /api/rights` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_project_write_dirs.py` prüft Hinzufügen, Entfernen, Zurücksetzen, Anwenden und die Tokenpflicht |
| API | `POST /api/sandbox` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_sandbox.py` prüft Ein-/Ausschalten, Werkzeuge, Prüfung und die Tokenpflicht gegen ein isoliertes Dashboard |
| API | `POST /api/new` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/roots` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/agent_template` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/agent` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, atomarer Write mit Prüfsummenkontrolle (V-005, `409 conflict` bei veraltetem `expected`), Browserworkflow nicht automatisiert geprüft (V-010) |
| API | `POST /api/costs` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_costs.py` prüft das Speichern von Nutzerpreisen je Projekt, die sofortige Neuberechnung, die Ablehnung ungültiger Preise ohne Schreibvorgang und die Persistenz; `tests/browser/test_costs_ui.py` prüft die Eingabe im Dashboard |
| API | `POST /api/mcp` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, JSONC-Verlustgrenzen (V-013) |
| API | `POST /api/profiles` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Anwendung nicht transaktional (V-012) |
| API | `POST /api/model` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/server` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/shutdown` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |

## 7. UI-Funktionen

Die Oberfläche ist eine eingebettete HTML/JS-Seite (`bin/vibe-web.py:209-410`).
In V-001 wurde sie nicht im Browser geöffnet; alle Einträge sind daher
„vorhanden, noch nicht geprüft“. Die beiden Zeilen zu den F3-Funktionen wurden
später ergänzt und in einem isolierten Dashboard mit Playwright (Chromium,
headless) geprüft.

| Typ | Funktion | Status | Beleg |
| --- | --- | --- | --- |
| UI | `Tab Projekte` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:237-291`; Projektliste, Detail, Roots, Neuanlage; kein Browsertest |
| UI | `Projektdetail: Struktur` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` `detail`/`detailTabs`/`showDetailTab`; feste Kopfleiste mit Laufzustand und Hauptaktionen, Kennzahlenkacheln und die Register Arbeit, Ausgabe, Assistent und Einstellungen mit ARIA-Verknüpfung und Tastaturbedienung; `tests/browser/test_project_detail_ui.py` prüft Standardbild, Maus- und Tastaturwechsel, Verknüpfung, sichtbare Hauptaktionen, Prüfungsausgabe und die schmale Ansicht (Chromium, headless); Screenshots `docs/features/F13-uebersicht.png` und `docs/features/F13-einstellungen.png` |
| UI | `Tab Agenten & Modelle` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:292-358`; Agentenliste, Formular, Roh-Editor, Profile; kein Browsertest |
| UI | `Tab MCP-Tools` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:360-406`; Liste, Formular, Test, Aktivierung; kein Browsertest |
| UI | `Tab Umgebung` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:548-568`; der Tab lädt Doctor- und Fritzbox-Karte; `tests/browser/test_fritz_ui.py` öffnet ihn (Chromium, headless, isoliertes Dashboard) |
| UI | `Tab Kosten` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` `costs`/`costDetail`; `tests/browser/test_costs_ui.py` prüft Projektübersicht, Paket-/Modellzeilen, Preiseingabe mit sofortiger Neuberechnung, Persistenz nach Neuladen und die Ablehnung unvollständiger Eingaben (Chromium, headless); Screenshot `docs/features/F12-kosten.png` |
| UI | `Tab Umgebung: Fritzbox-Reconnect` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:550-568`; `tests/browser/test_fritz_ui.py` zeigt „Automatik: aus“, schaltet die Automatik ein und aus, startet den manuellen Reconnect gegen eine Attrappe und prüft das Ergebnis; Screenshot `docs/features/F5-fritz.png` |
| UI | `Kopfzeile opencode Start/Stop` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:242-245`; ruft `POST /api/server`; kein Browsertest |
| UI | `Kopfzeile Dashboard beenden` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:244`; ruft `POST /api/shutdown`; kein Browsertest |
| UI | `Log-Stream` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:282-291`; EventSource auf `/api/stream`; kein Browsertest |
| UI | `Projektdetail: Schreibrechte` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:369-379`; `tests/browser/test_write_dirs_ui.py` bedient Liste, Hinzufügen, Entfernen, Zurücksetzen und Anwenden (Chromium, headless); die Liste begrenzt `edit`, nicht `bash` |
| UI | `Projektdetail: Sandbox` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:444-459`; `tests/browser/test_sandbox_ui.py` schaltet die Sandbox ein und aus, speichert Build-Werkzeuge, prüft den bereiten Zustand und den Hinweis in den Schreibrechten (Chromium, headless); Screenshot `docs/features/F7-sandbox.png` |
| UI | `Agenteneditor: Schreibrechts-Hinweis` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:434-444`; Hinweis und Vorlage folgen dem gewählten Bereich (global/projekt); `tests/browser/test_write_dirs_ui.py` (Chromium, headless) |
| UI | `Projektdetail: Arbeitspaket-Pause` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:356,371-375`; `tests/browser/test_pause_after_package_ui.py` fordert die Pause an, prüft den Zustand und hebt sie wieder auf (Chromium, headless); Screenshot `docs/features/F4-pause.png` |
| UI | `Projektliste: Pause-Markierung` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:330`; `tests/browser/test_pause_after_package_ui.py` prüft die Markierung „Pause“ in der Projektzeile (Chromium, headless) |
| UI | `Projektdetail: Projektassistent` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` `guideCard`/`drawGuide`; `tests/browser/test_project_guide_ui.py` listet die fachlichen Schritte, speichert Antworten, legt SPEC.md und fehlende Grundlagen an, lässt gefüllte Abschnitte unverändert und übernimmt einen Agenten-Entwurf erst auf Knopfdruck (Chromium, headless) |
| UI | `Projektdetail: Arbeitspakete und Bugs` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` `ticketCard`/`ticketFormCard`/`bugFormCard`; `tests/browser/test_tickets_ui.py` legt ein Arbeitspaket an, bearbeitet und löscht es und meldet einen Bug mit Kennzeichnung in der Feedback-Liste (Chromium, headless); Screenshot `docs/features/F15-arbeitspakete.png` |

## 8. Funktionsbereiche aus SPEC.md

| Bereich | Status | Bewertung |
| --- | --- | --- |
| Projekte und Entwicklungsordner | teilweise vorhanden | Einlesen, Liste, Detail, Roots vorhanden; gleichnamige Projekte werden nur als `name@root` unterschieden, URLs/IDs sind nicht kollisionsfrei (V-008) |
| Projektvorlagen | teilweise vorhanden | Sechs Typen plus `common` vorhanden (neu: `rebuild`); unbekannter Typ fällt still auf `generic` zurück; Android-Prüfung ist nicht global (V-008, F14) |
| Arbeitspakete und Feedback | teilweise vorhanden | Kommentare werden ignoriert, `BLOCKIERT` bleibt offen; Nachweisprüfung vorhanden; Feedback und Arbeitspakete sind über die Oberfläche anlegbar, bearbeitbar und löschbar, Bugs werden als Feedback mit `Art: Bug` gemeldet (F15); ID-Vergabe mit Prüfsummenwiederholung (V-009) |
| Agenten | teilweise vorhanden | Liste, Anlegen, Bearbeiten, Kopieren, Löschen, kollisionsfreie Sicherung und Wiederherstellung vorhanden; atomare Writes und Konflikterkennung über `vibe_storage` (V-005); verlustfreie Feldpflege und Browserworkflow fehlen (V-010) |
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
| Webserver-Sicherheit | vorhanden und automatisiert geprüft | Loopback-Bindung, Token, Host-/Origin-Prüfung, Requestlimit, strukturierte Fehler und Health in V-004; `tests/unit/test_web_api_security.py` prüft fehlendes/falsches Token, fremden Host/Origin, ungültiges JSON, fehlende Content-Length, übergroße Requests, parallele Anfragen und tokenfreie Logs |
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
   Request-Größe (`bin/vibe-web.py:116-121`). → V-004. **In V-004 behoben:**
   Query-Token nur noch für `/api/stream`, Host-/Origin-/Sec-Fetch-Site-Prüfung,
   1-MiB-Limit, strukturierte Fehler und tokenfreie Logs.
4. Feedback-IDs werden als „höchste vorhandene + 1“ ohne Sperre vergeben
   (`bin/vibe:257-259`). → V-009.
5. Profilanwendung schreibt Agenten nacheinander ohne Transaktion
   (`bin/vibe:497-513`). → V-012.
6. Agenten-/Konfigurationssicherungen nutzten Sekunden-Zeitstempel und waren
   nicht kollisionsfrei (`bin/vibe:384-386`, `bin/vibe_mcp.py:124-127`).
   **In V-005 behoben:** gemeinsame Storage-Schicht `bin/vibe_storage.py` mit
   atomarem Ersetzen, Sperre, Prüfsummenkontrolle, kollisionsfreien Sicherungen
   (`O_EXCL`, Mikrosekunden, Zufallsteil, Zähler) und Wiederherstellung; auf
   FUSE/NTFS wird keine Atomarität oder Rechtewirkung zugesichert.
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
| `fritz-reconnect.py` | in V-001 nur in der aktiven Installation | Seit F5 im Repository (`bin/fritz-reconnect.py`) und Teil des Manifests; `install-vibe.sh` kopiert den Helfer. Die Automatik bleibt standardmäßig aus und ist im Dashboard schaltbar. |
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
