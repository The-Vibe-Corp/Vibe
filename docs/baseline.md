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
| `scripts/setup-vibe.py` (F6) | Installation, Werkzeugprüfung, Wiederverwendung | `tests/unit/test_setup_vibe.py` (45 Tests) mit simulierten Plattformen und temporären Zielordnern | vorhanden und automatisiert geprüft (Linux/Container/Windows-Planung); kein echter Paketmanager- oder Windows-Lauf |
| `install-vibe.sh` (F6) | Kompatibler Linux-Einstieg | Wrapper-Test startet den echten Setup in temporärem `VIBE`/`HOME` | vorhanden und automatisiert geprüft |
| `setup-vibe.cmd` (F6) | Windows-Einstieg, bootstrappt Python über `winget` | nur statisch geprüft (Datei und Aufruf), kein Windows-Lauf | vorhanden, nicht auf Windows ausgeführt |
| npm (optional, F6) | Installation von `opencode` über `opencode-ai` | Aufrufplan im Test; `npm view opencode-ai name` in dieser Umgebung geprüft | vorhanden; nur mit Zustimmung ausgeführt |
| WSL2/Docker unter Windows (F6) | `tmux`/`flock` für Agentenläufe | nicht ausgeführt; Setup meldet die Grenze | fehlt nativ unter Windows; dokumentierte Voraussetzung |

Der Setup kopiert Programmdateien und Vorlagen, legt den Startbefehl an und
registriert vorhandene Git-Projekte. Laufzeitdaten (`vibe.json`,
`models.json`, `profiles.json`, `_logs`) und vorhandene
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
| CLI | `vibe runs` | vorhanden und automatisiert geprüft | `bin/vibe:1769-1815` (`cmd_runs`), Dispatch `bin/vibe:4577`; `tests/unit/test_run_control.py` prüft Liste und das Aufräumen verwaister Registereinträge ohne tmux-Sitzung, auch bei fehlendem Projektverzeichnis, sowie nicht prüfbare Sitzungen; es werden keine Sitzungen beendet |
| CLI | `vibe sessions` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_sessions`), Dispatch `"sessions": lambda: cmd_sessions(r)`; `tests/unit/test_ap19_sessions_cli.py` (19 Fälle nach Test-Runde 3) prüft Liste mit Zustandslabel/Agent/Projekt, Standard- und Parameterlimit, gespeichertes Limit, Projekt-/Textfilter (auch aus fremdem CWD und mit Ablehnung unbekannter Namen), Limit_Setzen inkl. Ablehnung sowie jede Resume-Ablehnung (unbekannt, fremdes Projekt, kein Treffer, aktiver Lauf, Pi) und den Start genau der gewählten Session über `VIBE_CONTINUE_SESSION`; `tests/unit/test_ap19_sessions_registry.py` (23 Fälle) prüft Register und Zustandsableitung, `tests/unit/test_ap19_runner_capture.py` (11 Fälle) die Erfassung im Filter |
| CLI | `vibe pause` | vorhanden und automatisiert geprüft | `bin/vibe:404-448`; `tests/unit/test_pause_after_package.py` prüft Anfordern, Status, Aufheben und die Ablehnung unbekannter Projekte ohne Markierung; `bin/vibe-run.sh:31-65` verbraucht die Markierung und startet kein neues Paket |
| CLI | `vibe keys` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_keys`, Dispatch `"keys": lambda: cmd_keys(r)`); `tests/unit/test_ap23_keys.py` (25 Verträge: add/select/list/remove, opencode-Auth-Sync/Reset, CLI `main`) |
| CLI | `vibe package` | vorhanden und automatisiert geprüft | `bin/vibe` (`package_close`, `cmd_package_close`, Dispatch `"package"`); seit AP4: `vibe package close <projekt> <id>` als zweite Abschlussphase für PR-only-Pakete — verifiziert per REST, dass der Merge-Request gemergt ist, holt den Integrationsstand per `fetch --prune` + `merge --ff-only` auf die Fernspitze, übernimmt `[x]`/Nachweis aus dem registrierten Worktree (inkl. Entfernen der BLOCKIERT-Marke), räumt worktree-bewusst auf und vergisst Registry-Eintrag und zugehörige Sessions; `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`PackageCloseCliTest`) prüft den Erfolg (Nachweis, Cleanup, Registry/Session entfernt), den nicht gemergten Fall (keine Änderungen) und die Ablehnung ohne aktive Verknüpfung; GUI-Aktion im Nova-Arbeiten-Reiter über `POST /api/package` |
| CLI | `vibe github` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_github`, `github_cli`, Dispatch `"github": lambda: github_cli(r)` — Symbolnamen statt Zeilenbereiche gegen künftige Versätze); `tests/unit/test_ap06_github.py` prüft Status, Branches, Abruf, Pull (mit --ff-only), Push, Issues, Import, Merge-Request (Default-Basis, zweistufige Freigabe) samt Tokenpflicht (401 ohne `GITHUB_TOKEN`) und verständlichen Meldungen; `tests/browser/test_ap06_github_ui.py` prüft die Karte „Git & GitHub“. Seit AP9 (Test: `tests/unit/test_ap9_github.py`): Aktionen `checkout` (Branch auschecken, erzeugt fehlende aus origin/<name>), `push` mit `--branch`/Ziel-Branch, `test` (Verbindungsprüfung), `token` (je Projekt verschlüsselt), `github pr --branch`, `vibe clone --branch`; Läufer-Subkommandos `vibe_packages.py github-pull`/`github-complete` (`tests/unit/test_ap9_runner_github.py`) |
| CLI | `vibe ask` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_ask`); `tests/unit/test_questions.py` prüft Stellen mit Auswahl, Projektableitung, Ablehnung unbekannter Projekte, Zeitlimit mit Exit-Code 3 und Fortsetzen mit `--wait`; `tests/browser/test_questions_ui.py` zeigt die Frage samt Vorschlägen im Dashboard |
| CLI | `vibe questions` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_questions`); `tests/unit/test_questions.py` prüft die Liste offener Fragen mit nummerierten Vorschlägen |
| CLI | `vibe answer` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_answer`); `tests/unit/test_questions.py` prüft Auswahl- und freie Antwort sowie die Quelle `--by agent`; `tests/unit/test_questions.py` und `tests/browser/test_questions_ui.py` prüfen die Ablehnung einer zweiten Antwort |
| CLI | `vibe autonomous` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_autonomous`); `tests/unit/test_questions.py` prüft Ein/Aus/Status je Projekt, die sofortige Entscheidung im aktiven Modus und den Abbruch eines laufenden Wartens beim Einschalten |
| CLI | `vibe verify` | teilweise vorhanden | `bin/vibe:244-255`; Fehlerfall ohne Prüfbefehl ausgeführt (Exit 1); Rückgabecode des Prüfbefehls wird nicht weitergereicht |
| CLI | `vibe feedback` | vorhanden, noch nicht geprüft | `bin/vibe:257-274`; interaktiver Schreibvorgang, nicht ausgeführt |
| CLI | `vibe new` | vorhanden, noch nicht geprüft | `bin/vibe:308-327`; legt Projekt und Git-Repo an, nicht ausgeführt |
| CLI | `vibe init` | vorhanden, noch nicht geprüft | `bin/vibe:300-306`; schreibt Vorlagen, nicht ausgeführt |
| CLI | `vibe roots` | vorhanden und manuell geprüft | `bin/vibe:135-151`; ausgeführt, Exit 0, ein Entwicklungsordner mit 7 Projekten |
| CLI | `vibe scan` | vorhanden und manuell geprüft | `bin/vibe:653`; Alias auf `cmd_roots()`, ausgeführt, Exit 0 |
| CLI | `vibe agents` | vorhanden und manuell geprüft | `bin/vibe:349-364,428-435`; ausgeführt, Exit 0, globale Agenten plausibel |
| CLI | `vibe rights` | vorhanden und automatisiert geprüft | `bin/vibe:371-386`; `tests/unit/test_project_write_dirs.py` prüft Liste, Hinzufügen, Entfernen und Zurücksetzen ohne Schreibzugriff auf produktive Konfiguration |
| CLI | `vibe sandbox` | vorhanden und automatisiert geprüft | `bin/vibe:388-474`; `tests/unit/test_sandbox.py` prüft Status, Ein-/Ausschalten, Werkzeugliste, Ablehnung von Steuerzeichen, bubblewrap-Argumente, die `/tmp`-Grenze, die schreibgeschützte `.vibe`-Konfiguration und echte sandboxed Schreibversuche |
| CLI | `vibe priority` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_priority`, AP11); `tests/unit/test_ap11_priority.py` prüft Anzeige der konfigurierten und effektiven Reihenfolge, Ablehnung unbekannter Kennungen ohne Schreiben, Dubletten-Reduktion, atomare Ablage von `PACKAGE_ORDER` inkl. CRLF-Erhalt und Leeren mit Rückfall auf die Standardordnung |
| CLI | `vibe agent` | vorhanden, noch nicht geprüft | `bin/vibe:441-457`; `new/edit/show/rm`, Editor und Schreibzugriff nicht ausgeführt |
| CLI | `vibe models` | vorhanden und manuell geprüft | `bin/vibe:459-466`; ausgeführt, Exit 0; Daten aus `data/models.json` bleiben ungeprüfte Altdaten (V-011) |
| CLI | `vibe harness` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_harness`), `bin/vibe_harness.py`; `tests/unit/test_ap04_harness.py` prüft Status, Auswahl, ungültige Namen, beschädigte Auswahl, Diagnose und Einrichtungsplan; `tests/unit/test_ap04_setup_harness.py` prüft die Auswahl im Setup |
| CLI | `vibe limits` | fehlt | Die Einstellung „Run behaviour" und ihre Funktion wurden vollständig entfernt; eine vorhandene `limits.json` wird ignoriert. `tests/unit/test_limits.py` prüft, dass der Befehl nichts persistiert und Quota-/Anmeldefehler immer sofort anhalten. |
| CLI | `vibe gates` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_gates`), `bin/vibe_gates.py`; `tests/unit/test_ap10_gates.py` prüft Status mit Herkunft, globales und projektspezifisches Setzen, Entfernen mit leerem Wert, Ablehnung Unbekannter/Ungültiger ohne Schreiben, defekte Dateien und die wirksamen Schranken im Läufer inkl. Schranken-Rückfrage |
| CLI | `vibe model` | vorhanden, noch nicht geprüft | `bin/vibe:468-477`; schreibt Agentendatei, nicht ausgeführt |
| CLI | `vibe profile` | teilweise vorhanden | `bin/vibe:515-528`; Liste ausgeführt, Exit 0; `use` schreibt Agenten und wurde nicht ausgeführt (V-012) |
| CLI | `vibe costs` | vorhanden und automatisiert geprüft | `bin/vibe:1835-1873` (`cmd_costs`); `tests/unit/test_costs.py` prüft Übersicht, Paketzeilen, Summen, unbekannte Preise (0 €) und die Ausgabe in Euro; seit GH-99 stammt die Anzeige aus den persistenten Paketkosten, die opencode-Datenbank wird nur beim Spülen gelesen |
| CLI | `vibe mcp` | teilweise vorhanden | `bin/vibe:584-586`, `bin/vibe_mcp.py:335-358`; `list` ausgeführt (Exit 0), `show/test/on/off/rm` nicht geprüft; Transport-/Limitgrenzen fehlen (V-013/V-014) |
| CLI | `vibe emu` | vorhanden, noch nicht geprüft | `bin/vibe:531-534`; startet Emulator, nicht ausgeführt |
| CLI | `vibe ui` | vorhanden, noch nicht geprüft | `bin/vibe:550-560`; startet Dashboard in tmux, nicht ausgeführt |
| CLI | `vibe server` | vorhanden, noch nicht geprüft | `bin/vibe:540-548`; opencode-Prozessverwaltung, nicht ausgeführt |
| CLI | `vibe types` | vorhanden und manuell geprüft | `bin/vibe:277-285`; ausgeführt, Exit 0, fünf Typen plus `common` |
| CLI | `vibe doctor` | vorhanden und manuell geprüft | `bin/vibe:562-582`; ausgeführt, Exit 0, Umgebungsprüfungen plausibel |
| CLI | `vibe paths` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_paths`), `bin/vibe_paths.py`; `tests/unit/test_vibe_paths.py` prüft JSON-Ausgabe, Dev-Profil mit eigenen Ports, persönliche Einstellungen, Pfade mit Leerzeichen, ungültige Ports und unbekannte Argumente; die Abfrage legt keine Verzeichnisse an |
| CLI | `vibe clone` | vorhanden und automatisiert geprüft | `bin/vibe` (`cmd_clone`, Dispatcher-Eintrag `clone`); `tests/unit/test_ap8_github_checkout.py` prüft das Auschecken aus lokalen Git-Remotes (file://-Bare-Repositories), die Übernahme lokaler Einstellungen (project.env, Agenten, Test-Agent, Vorlagen), Fehlerfälle mit Cleanup und die CLI (`CommandLineTest`); Browserworkflow in `tests/browser/test_ap8_checkout_ui.py` |
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
| API | `GET /api/agents` | vorhanden und automatisiert geprüft | `do_GET`; Transportprüfung zentral in V-004; GH-57: die Antwort trägt zusätzlich `models_stand`/`models_error` (Modellliste aus dem Zustands-Cache, falls vorhanden, sonst Live-Lauf des Harness) sowie `default_models` (Rolle → Modell aus den Agent-Einstellungen) und `standard_profiles` (`default`,`free`,`mid`,`high`); `tests/unit/test_gh57_settings_backend.py` (`ModelsRefreshTest`, `ModelsBrokenApiTest`) prüft Cache-Nutzung ohne erneuten Harness-Lauf, Fehlermeldung ohne Cache-Veränderung und die Zusatzfelder |
| API | `POST /api/agents` | vorhanden und automatisiert geprüft | `do_POST` (GH-57); einzige Aktion `refresh_models` ruft die Modelle des aktiven Harness live ab, schreibt sie atomar als `<Zustand>/models-cache.json` (mit ISO-8601-UTC-`stand`) und antwortet mit der frischen Ansicht; bei Harness-Fehler `ok:false` ohne Cache-Veränderung; unbekannte Aktion wird abgelehnt; `tests/unit/test_gh57_settings_backend.py` (`ModelsRefreshTest.test_refresh_models_writes_the_cache_and_answers_fresh`, `ModelsBrokenApiTest`) prüft Cache-Schreibvorgang, Stand-Feld und Fehlerpfad; `tests/browser/test_gh57_settings_ui.py` (`ModelsSectionTest`) prüft den Aktualisieren-Knopf und die Datumanzeige |
| API | `GET /api/costs` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_costs.py` prüft Übersicht, Projektdetail, Tokenpflicht (403) und unbekanntes Projekt (404); `tests/browser/test_costs_ui.py` öffnet die Kostenansicht im Browser |
| API | `GET /api/agent` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/mcp` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/mcp_entry` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/types` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/doctor` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/questions` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_questions.py` prüft offene Fragen mit Vorschlägen, leere Liste nach der Antwort und die Tokenpflicht (403) |
| API | `POST /api/questions` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_questions.py` prüft Auswahl- und freie Antwort, Rückgabe der neuen offenen Liste, Ablehnung ungültiger IDs/Auswahlen, unbekannter Aktionen und einer zweiten Antwort ohne Überschreiben |
| API | `GET /api/autonomous` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_questions.py` prüft den Zustand je Projekt, unbekannte Projekte (404) und die Tokenpflicht (403) |
| API | `POST /api/autonomous` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_questions.py` prüft Ein- und Ausschalten, die gespeicherte Datei, unbekannte Aktionen (400) und die Tokenpflicht (403) |
| API | `GET /api/server` | vorhanden, noch nicht geprüft | `do_GET`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/harness` | vorhanden und automatisiert geprüft | `do_GET`; `tests/browser/test_ap04_harness_ui.py` öffnet die Umgebungsansicht über das echte Dashboard und prüft den aktiven Harness und die Pi-Einrichtungshinweise; `bin/vibe_harness.py` liefert die Auswahl |
| API | `POST /api/harness` | vorhanden und automatisiert geprüft | `do_POST`; `tests/browser/test_ap04_harness_ui.py` wechselt den Harness, prüft die gespeicherte Auswahl nach dem Neuladen und den sichtbaren Einrichtungsplan |
| API | `GET /api/stream` | teilweise vorhanden | `stream()`; Token nur im Query-String (EventSource), Host geprüft; Origin nicht anwendbar; nicht ausgeführt |
| API | `POST /api/run` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/stop` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/pause` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_pause_after_package.py` prüft Anfordern, Aufheben, unbekannte Aktion und wahrheitsgemäße Meldung; `tests/unit/test_web_api_security.py` nutzt die Route für Token-, Host-, Origin-, JSON- und Größenprüfungen |
| API | `GET /api/subagents` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_output_view_f19_api.py` prüft Tokenpflicht (403), erfasste Subagenten aus `<log>.state.json` und die leere Liste ohne Zustandsdatei (keine Attrappen). F24 ergänzt `agent`: Name des Agenten aus dem aktiven Laufregistereintrag (`starting`/`running`); ohne aktiven Lauf fehlt das Feld — geprüft in `tests/unit/test_f24_output_agent_ui.py` |
| API | `GET /api/subagent-output` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_output_view_f19_api.py` prüft die Ausgabe eines erfassten Subagenten sowie `ok:false` mit Meldung für unbekannte Sessions und Subagenten ohne Live-Ausgabe (kein HTTP-Fehler) |
| API | `POST /api/steer` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_output_view_f19_api.py` prüft Tokenpflicht (403), Ablehnung ohne aktiven Lauf, ohne Session, ohne Kennwort und bei unerreichbarem Server sowie die echte Zustellung per HTTP Basic-Auth und die Kennzeile im Laufprotokoll |
| API | `POST /api/continue` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_ap14_output_view_api.py` prüft Tokenpflicht (403), Ablehnung bei aktivem Lauf, ohne erfasste Session und bei Pi (Print-Modus) sowie den erfolgreichen Startbefehl mit `VIBE_CONTINUE_SESSION`-Export; `tests/unit/test_ap14_runner_continue.py` prüft die Validierung und die Fortsetzungskette im Läufer; `tests/browser/test_ap14_output_ui.py` prüft die Fortsetzen-Schaltfläche im Dashboard |
| API | `GET /api/sessions` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_ap19_sessions_api.py` (17 Fälle) prüft Tokenpflicht (403), unbekanntes Projekt (404), alle Vertragsfelder samt Zustandslabel und Reihenfolge, Rangfolge und Deckelung des Limits, Textfilter, `running` aus dem Laufregister sowie `resume_supported` für opencode und Pi; `tests/browser/test_ap19_sessions_ui.py` (7 Fälle) prüft die zugehörige Karte; alle AP19-Suiten zusammen nach Runde 3: 77 Fälle grün (23 Registry + 11 Erfassung + 19 CLI + 17 API + 7 Browser) |
| API | `POST /api/sessions` | vorhanden und automatisiert geprüft | `do_POST`, POST-Whitelist; `tests/unit/test_ap19_sessions_api.py` prüft Tokenpflicht (403, kein Start), Ablehnung unbekannter/fremder Session, aktiven Lauf, Pi (`--no-session`) und unbekannte Aktion sowie den erfolgreichen Fortsetzungsstart mit genau dem `VIBE_CONTINUE_SESSION`-Export der gewählten Session; `tests/browser/test_ap19_sessions_ui.py` prüft den exakten POST-Payload und die Tastaturbedienung |
| API | `POST /api/verify` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/init` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/feedback` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_feedback_capture.py` prüft Anlegen mit Titel und Beschreibung, Ablehnung fehlender Titel und Tokenpflicht; `tests/unit/test_work_packages.py` prüft die Bugmeldung mit `kind: "bug"` und die Kennzeichnung in der Projektdetail-Antwort; ID-Vergabe mit Prüfsummenwiederholung (V-009) |
| API | `POST /api/ticket` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_work_packages.py` prüft Anlegen, Bearbeiten und Löschen von Arbeitspaketen, doppelte oder ungültige IDs, unbekannte IDs und Aktionen ohne Dateiänderung |
| API | `GET /api/guide` | vorhanden und automatisiert geprüft | `do_GET`; `tests/unit/test_project_guide.py` prüft Schritte, Dateien, Entwürfe, Agentenzustand und die Tokenpflicht |
| API | `GET /api/agents_file` | vorhanden und automatisiert geprüft | `do_GET` (F31); F34 zusätzlich: die Antwort listet die vorhandenen Sicherungen der Datei (Dateinamen mit Zeitstempel, neueste zuerst) als `backups`; `tests/unit/test_f31_agents_file.py` prüft die View (existiert, Blocktrennung, fehlende Datei) und die Pfadsicherung; `tests/browser/test_f31_agents_file_ui.py` liest die View im Dashboard; `tests/unit/test_f34_backend.py` prüft die Sicherungsliste |
| API | `POST /api/agents_file` | vorhanden und automatisiert geprüft | `do_POST` (F31); `tests/unit/test_f31_agents_file.py` prüft Speichern mit byte-identisch erhaltenem Legacy-Block, blockfreie Dateien als `before + after`, Digest-Ablehnung, Marker-Ablehnung und Anlegen aus der Vorlage; `tests/browser/test_f31_agents_file_ui.py` prüft Bearbeiten beider Teile, Speichern, Anlegen und die Ablehnung unbekannter Aktionen |
| API | `POST /api/guide` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_project_guide.py` prüft Speichern mit Dateianlage, Ablehnung unbekannter Schritte ohne Schreiben sowie Übernehmen und Verwerfen von Entwürfen |
| API | `POST /api/rights` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_project_write_dirs.py` prüft Hinzufügen, Entfernen, Zurücksetzen, Anwenden und die Tokenpflicht |
| API | `POST /api/sandbox` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_sandbox.py` prüft Ein-/Ausschalten, Werkzeuge, Prüfung und die Tokenpflicht gegen ein isoliertes Dashboard |
| API | `GET /api/priority` | vorhanden und automatisiert geprüft | `do_GET` über `vibe_services.priority_info`; `tests/browser/test_ap11_priority_ui.py` prüft die Ansicht (Status je Eintrag, effektive Reihenfolge, Meldung) gegen ein isoliertes Dashboard |
| API | `POST /api/priority` | vorhanden und automatisiert geprüft | `do_POST`; `tests/browser/test_ap11_priority_ui.py` prüft Speichern (Schreibt `PACKAGE_ORDER` in `.vibe/project.env`) und Leeren über die Oberfläche, `tests/unit/test_ap11_priority.py` die Ablehnung unbekannter Kennungen |
| API | `POST /api/login` | vorhanden und automatisiert geprüft | `do_POST` (AP13); `tests/unit/test_ap13_web_access.py` prüft Anmeldung mit Instanz-Token oder Kennwort (gesalzener Hash), Session-Cookie `vibe_session` (HttpOnly, SameSite=Strict, Path=/), strukturierte 403-Ablehnung ohne Kennwort-/Token-Auskunft; `tests/browser/test_ap13_security_ui.py` prüft den Eintausch von `#t=` gegen den Cookie und die Anmeldekarte |
| API | `POST /api/logout` | vorhanden und automatisiert geprüft | `do_POST` (AP13); `tests/unit/test_ap13_web_access.py` prüft, dass die Session endet und weitere Anfragen ohne Berechtigung mit 403 `unauthorized` abgelehnt werden |
| API | `GET /api/security` | vorhanden und automatisiert geprüft | `do_GET` (AP13); `tests/unit/test_ap13_web_access.py` prüft Ansicht von Port/Bind/Allowlist/Passwortstatus/`restart_required` sowie die Authentisierungspflicht; `tests/browser/test_ap13_security_ui.py` prüft die Karte „Zugriffssicherheit" |
| API | `POST /api/security` | vorhanden und automatisiert geprüft | `do_POST` (AP13); GH-57 ergänzt Aktion `restart`: Antwort sofort mit geplantem Port/Bind (aus ui.json) und dem aktuellen Token (über `extra`, Meldungen bleiben redaktiert), danach geordneter Neustart per `os.execv` mit `VIBE_WEB_KEEP_TOKEN=1` (Session-Token bleibt erhalten); `tests/unit/test_ap13_web_access.py` prüft Speichern von Port/Bind/Allowlist in ui.json (Validierung vor dem Schreiben, 400 ohne Dateiänderung bei ungültiger Eingabe, Neustart-Markierung) sowie Passwort setzen/löschen; `tests/unit/test_gh57_settings_backend.py` (`SecurityRestartTest`, `PrepareRuntimeTokenTest`) prüft Antwortfelder, erneute Erreichbarkeit am geplanten Port, Token-Erhalt und `restart_required=false` danach; `tests/browser/test_ap13_security_ui.py` prüft Portänderung mit Neustart-Hinweis und Passwortanmeldung; `tests/browser/test_gh57_settings_ui.py` (`AccessSectionTest`) prüft Bestätigung und abgefangenen Neustart-POST |
| API | `POST /api/new` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/roots` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/agent_template` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/agent` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, atomarer Write mit Prüfsummenkontrolle (V-005, `409 conflict` bei veraltetem `expected`), Browserworkflow nicht automatisiert geprüft (V-010) |
| API | `POST /api/clone` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` (`/api/clone`, ruft `vibe.checkout_from_github`); `tests/browser/test_ap8_checkout_ui.py` prüft Anlage des Projekts mit Übernahme der lokalen Einstellungen, Fehlermeldung bei ungültiger URL und Tokenpflicht; Transportprüfung zentral in V-004 |
| API | `POST /api/package` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` (`/api/package`, guarded wie die übrigen projektebezogenen Endpunkte: `known(name)` + Schreibschutz); seit AP4: Aktion `close` ruft `vibe.package_close(name, id)` — dieselbe zweite Abschlussphase wie `vibe package close` (PR-Merge per REST verifizieren, Integrationsstand auf Fernspitze, Nachweis aus dem registrierten Worktree, worktree-bewusstes Cleanup, Registry/Session vergessen); `tests/unit/test_ap4_korbat_gui.py` prüft Endpunkt-Verkabelung und Guard, `tests/unit/test_ap4_korbat_worktrees_sessions.py` (`PackageCloseCliTest`) die Fachfunktion; GUI-Aktion „Paket abschließen“ im Nova-Arbeiten-Reiter |
| API | `POST /api/github` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` (`/api/github`); Aktionen settings/link/unlink/fetch/pull/push/issues-sync/issues-state/pr, Pull nur mit `--ff-only` und Merge-Request nur mit ausdrücklicher Bestätigung (`confirm`); Transportprüfung zentral in V-004 (Pfad-Whitelist), Fachprüfung `tests/unit/test_ap06_github.py`, Karte im Projekt-Detail `tests/browser/test_ap06_github_ui.py`. Seit AP9: `checkout`, `push` mit `branch`/`target`, `connection` (Fern- + REST-Prüfung), `token.save`/`token.clear` (je Projekt verschlüsselt), `settings` persistiert `GITHUB_BASE`; `tests/unit/test_b7_github_auth.py` und `tests/browser/test_ap9_github_ui.py` prüfen die Erweiterungen. Seit GH-47: die getrennten Aktionen `issues`/`import` sind entfallen; der Issues-Weg läuft ausschließlich über `issues-sync` (Pull+Push+Text+Close) und `issues-state` (Label-Zustand) |
| API | `POST /api/costs` | vorhanden und automatisiert geprüft | `do_POST`; `tests/unit/test_costs.py` prüft das Speichern von Nutzerpreisen je Projekt, die sofortige Neuberechnung, die Ablehnung ungültiger Preise ohne Schreibvorgang und die Persistenz; `tests/browser/test_costs_ui.py` prüft die Eingabe im Dashboard |
| API | `POST /api/mcp` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, JSONC-Verlustgrenzen (V-013) |
| API | `POST /api/profiles` | vorhanden und automatisiert geprüft | `do_POST`; GH-57 erweitert: `save` mischt benannte Profile (statt zu ersetzen) und lehnt ein nicht-leeres `default`-Profil ab; `create`/`delete` (Standardprofile geschützt, Sicherung nach `<Zustand>/profile-backups`, `aktiv`-Fallback auf `default`); `backup`/`restore` (Restore nur mit `confirm:true`, Sicherheits-Snapshot vorher); `use` löst je Rolle die Kette Profilwert → Rollenmodell (erster globaler Agent der Rolle) → Vibe-Agent-Modell auf, prüft aufgelöste Werte auf Verfügbarkeit und überspringt leere Ketten mit Hinweis; `tests/unit/test_gh57_settings_backend.py` (`ProfilesSeedTest`, `ProfilesApiTest`, `ProfilesApplyFallbackTest`) prüft Seeding, Altbestand-Erhalt, Schutzwahrung, Mischung, Backup/Restore und die Fallback-Kette end-to-end |
| API | `POST /api/model` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/server` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `POST /api/shutdown` | vorhanden, noch nicht geprüft | `do_POST`; Transportprüfung zentral in V-004, Fachfunktion nicht ausgeführt |
| API | `GET /api/language` | vorhanden und automatisiert geprüft | `do_GET` (`language_data()`); liefert die globale Sprache aus `ui.json` mit `languages` (`en`, `de`) und `default` (`en`); `tests/unit/test_ap21_i18n.py` (`GlobalLanguageServerTest`) prüft die Antwort, den gespeicherten Wert und die Tokenpflicht (403) |
| API | `POST /api/language` | vorhanden und automatisiert geprüft | `do_POST`; validiert über `vibe_ui_config.validate_language`, schreibt `ui.json` über `vibe_ui_config.save` und lädt sie neu; ungültige Werte → 400 `invalid_language` ohne Schreiben; geprüft in `tests/unit/test_ap21_i18n.py` und `tests/browser/test_ap21_i18n_ui.py` |
| API | `GET /api/limits` | fehlt | Die Route existiert nicht mehr; `tests/unit/test_web_routes.py` (`LimitsRemovalApiTest`) prüft, dass eine alte `limits.json` weder Fehler noch Laufverhalten bewirkt. |
| API | `POST /api/limits` | fehlt | Die Route existiert nicht mehr und speichert nichts; geprüft in `tests/unit/test_web_routes.py` (`LimitsRemovalApiTest`). |
| API | `GET /api/gates` | vorhanden und automatisiert geprüft | `do_GET` (`_gates_view()`); wirksame Schranken global oder mit `?name=<projekt>` (Projekt wird geprüft), je Schlüssel `value`/`origin` plus `lines` und `problems`; `tests/unit/test_ap22_web_routes.py` (`GatesApiTest`) prüft Defaults, Projektansicht und Tokenpflicht |
| API | `POST /api/gates` | vorhanden und automatisiert geprüft | `do_POST` (`_gates_set()`); prüft Schlüssel (`vibe_gates.DEFAULTS`) und Wert vor dem Schreiben; global über `vibe_gates.save`, mit `project` als Override in `.vibe/project.env`; leerer Wert mit Projekt entfernt die Zeile; ungültige Eingaben ändern nichts; F34 zusätzlich: `values` als Map überträgt alle Zeilen gesammelt mit derselben Validierung; `tests/unit/test_ap22_web_routes.py` (`GatesApiTest`) und `tests/unit/test_f34_backend.py` (`GatesCollectedTest`) |
| API | `GET /api/paths` | vorhanden und automatisiert geprüft | `do_GET`; gibt `PATHS.as_dict()` (aufgelöste Pfade, Ports, opencode-URL) zurück, ohne Token oder Kennwörter; `tests/unit/test_ap22_web_routes.py` (`PathsApiTest`) prüft Tokenpflicht und Geheimnisfreiheit |
| API | `GET /api/runs` | vorhanden und automatisiert geprüft | `do_GET` (`_runs_view()`); Registerzeilen unverändert, neueste zuerst; `tests/unit/test_ap22_web_routes.py` (`RunsApiTest`) prüft leeres Register, Tokenpflicht und die Form der Antwort |
| API | `POST /api/runs` | vorhanden und automatisiert geprüft | `do_POST` (`_runs_prune()`); Aktion `prune` beendet verwaiste Live-Einträge, deren tmux-Sitzung fehlt, lässt laufende und nicht prüfbare unverändert (beendet nie eine Sitzung) und meldet `ended`/`running`/`unknown` plus `lines`; Aktion `cleanup` (F34) entfernt nur abgeschlossene Einträge und meldet `removed`/`remaining`; `tests/unit/test_ap22_web_routes.py` (`RunsApiTest`) prüft No-op auf leerem Register und unbekannte Aktion; `tests/unit/test_f34_backend.py` (`RunCleanupTest`) prüft Cleanup |
| API | `GET /api/ui_settings` | vorhanden und automatisiert geprüft | `do_GET` (F34); liest `currency` (EUR/USD) und `usd_rate` aus `<state>/ui.json`; `tests/unit/test_f34_backend.py` (`CurrencyUiSettingsTest`) prüft Tokenpflicht (403), Standardwerte und die Antwort |
| API | `POST /api/ui_settings` | vorhanden und automatisiert geprüft | `do_POST` (F34); schreibt `currency` und `usd_rate` atomar, lehnt ungültige Werte ab; `tests/unit/test_f34_backend.py` (`CurrencyUiSettingsTest::test_ui_settings_api_reads_and_writes_currency_atomically`) prüft Lesen/Schreiben mit und ohne Token |
| API | `POST /api/emu` | vorhanden und automatisiert geprüft | `do_POST` (`_emu()`); startet/stoppt `scripts/emulator-<aktion>.sh` des ersten Android-Projekts im Hintergrund (Argumentliste, keine Shell), sonst 200 `ok:false` mit Meldung; `tests/unit/test_ap22_web_routes.py` (`EmuApiTest`) prüft Ablehnung ohne Android-Projekt und Tokenpflicht |
| API | `GET /api/global_agents_file` | vorhanden und automatisiert geprüft | `do_GET` (F33); liefert `vibe.global_agents_view()` — Inhalt der globalen AGENTS.md mit `digest` und Pfadhinweis, fehlende Datei als View mit `exists:false` und leerem Text ohne Fehler, Symlink gilt als fehlend und wird nicht gelesen; `tests/unit/test_f33_global_agents.py` (`GlobalAgentsViewTest`, `GlobalAgentsApiTest`) prüft leere View, Digest-Antwort und Pfadsicherung |
| API | `POST /api/global_agents_file` | vorhanden und automatisiert geprüft | `do_POST` (F33); Aktion `save` schreibt UTF-8 mit Digest-Schutz (veralteter oder fehlender Digest wird ohne Schreiben abgelehnt, Symlink abgelehnt, Ziel bleibt unberührt), Aktion `create` legt die Vorlage nur an, wenn die Datei fehlt (kein Überschreiben, Symlink abgelehnt), unbekannte Aktion → 400 `rejected` (Handlerverhalten, ohne eigenen Testfall); GH-57 ergänzt `backup` (Sicherung nach `<Zustand>/global-agents-backups`; fehlende Datei wird abgelehnt) und `restore` (nur mit `confirm:true`, Sicherheits-Snapshot vorher, Antwort mit frischer Ansicht inkl. `backups`); die `GET`-Ansicht listet `backups`; `tests/unit/test_f33_global_agents.py` (`GlobalAgentsSaveTest`, `GlobalAgentsCreateTest`, `GlobalAgentsApiTest`); `tests/unit/test_gh57_settings_backend.py` (`GlobalAgentsFileTest`) prüft Backup-Pflicht, Restore mit/ohne Bestätigung und die Backups-Liste |
| API | `GET /api/settings` | vorhanden und automatisiert geprüft | `do_GET` (GH-117); liefert die versionierte Ansicht aus `<state>/settings.json` mit `stored`, `version` und den fünf effektiven Einstellungen (fehlende/ungültige Werte einzeln auf Defaults), ohne Geheimnisse; `tests/unit/test_settings_storage.py` (`SettingsApiTest`) prüft Tokenpflicht, Standardwerte, HTML-Meta und Persistenz über einen Serverneustart |
| API | `POST /api/settings` | vorhanden und automatisiert geprüft | `do_POST` (GH-117); misst ein Teil-Patch schlüsselweise in die Einstellungsdatei (atomar, unbekannte Schlüssel und höhere Version bleiben erhalten), meldet verworfene Schlüssel unter `ignored`; `tests/unit/test_settings_storage.py` (`SettingsApiTest`) prüft Schreiben aller fünf Werte, Ablehnung eines Nicht-Objekts und Tokenpflicht |

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
| UI | `Tab Umgebung` | vorhanden und automatisiert geprüft | `bin/web/nova-evals.js` (`nvEvalLoadEnvironment`); der Tab lädt Prüfungen, Pfade und Harness-Status; `tests/browser/test_activity_ui.py` prüft Doctor-Zeilen, Pfade und Harness-Status (Chromium, headless, isoliertes Dashboard) |
| UI | `Tab Kosten` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` `costs`/`costDetail`; `tests/browser/test_costs_ui.py` prüft Projektübersicht, Paket-/Modellzeilen, Preiseingabe mit sofortiger Neuberechnung, Persistenz nach Neuladen und die Ablehnung unvollständiger Eingaben (Chromium, headless); Screenshot `docs/features/F12-kosten.png` |
| UI | `Projektliste: GitHub-Auschecken` | vorhanden und automatisiert geprüft | `bin/web/app.js` (`newForm`); Karte „Neues Projekt“ mit URL-Feld und Knopf „Aus GitHub auschecken“; `tests/browser/test_ap8_checkout_ui.py` prüft Karte, Auschecken mit Öffnen des Projektdetails, Fehlermeldung mit nutzbarer Karte und die Projektleiste (Chromium, headless) |
| UI | `Kopfzeile opencode Start/Stop` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:242-245`; ruft `POST /api/server`; kein Browsertest |
| UI | `Kopfzeile Dashboard beenden` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:244`; ruft `POST /api/shutdown`; kein Browsertest |
| UI | `Log-Stream` | vorhanden, noch nicht geprüft | `bin/vibe-web.py:282-291`; EventSource auf `/api/stream`; kein Browsertest |
| UI | `Projektdetail: Ausgabe (Syntax, Steuerung, Subagenten)` | vorhanden und automatisiert geprüft | `bin/web/app.js` `outputView`/`hlLine`/`renderLogChunk` mit gemeinsamem DOM-only-Highlighter; B11 zeigt Hauptagent und alle laufenden Subagenten gleichzeitig mit Zielauswahl, Zusatzanweisung und Fortsetzen; AP20 ergänzt kompakte Übersicht, umbrechendes Kartenraster und einen einzigen Scrollbereich je Modus (Fokus-Modus für die vollständige Ausgabe). `tests/unit/test_output_view_f19_runner.py` und `tests/unit/test_output_view_f19_api.py` prüfen Protokollfilter, Subagenten-Zustand und die Steuer-API; Browserabnahmen `tests/browser/test_b11_output_ui.py`, `test_f30_subagent_view_ui.py`, `test_b14_subagent_output_ui.py`, `test_ap16_syntax_highlighting_ui.py` und `test_ap20_output_overview_ui.py`; Screenshots `docs/features/F19-ausgabe.png`, `docs/features/AP20-ausgabe.png` |
| UI | `Projektdetail: Schreibrechte` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:369-379`; `tests/browser/test_write_dirs_ui.py` bedient Liste, Hinzufügen, Entfernen, Zurücksetzen und Anwenden (Chromium, headless); die Liste begrenzt `edit`, nicht `bash` |
| UI | `Projektdetail: Sandbox` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:444-459`; `tests/browser/test_sandbox_ui.py` schaltet die Sandbox ein und aus, speichert Build-Werkzeuge, prüft den bereiten Zustand und den Hinweis in den Schreibrechten (Chromium, headless); Screenshot `docs/features/F7-sandbox.png` |
| UI | `Agenteneditor: Schreibrechts-Hinweis` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:434-444`; Hinweis und Vorlage folgen dem gewählten Bereich (global/projekt); `tests/browser/test_write_dirs_ui.py` (Chromium, headless) |
| UI | `Projektdetail: Arbeitspaket-Pause` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:356,371-375`; `tests/browser/test_pause_after_package_ui.py` fordert die Pause an, prüft den Zustand und hebt sie wieder auf (Chromium, headless); Screenshot `docs/features/F4-pause.png` |
| UI | `Projektliste: Pause-Markierung` | vorhanden und automatisiert geprüft | `bin/vibe-web.py:330`; `tests/browser/test_pause_after_package_ui.py` prüft die Markierung „Pause“ in der Projektzeile (Chromium, headless) |
| UI | `Projektdetail: Projektassistent` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` `guideCard`/`drawGuide`; `tests/browser/test_project_guide_ui.py` listet die fachlichen Schritte, speichert Antworten, legt SPEC.md und fehlende Grundlagen an, lässt gefüllte Abschnitte unverändert und übernimmt einen Agenten-Entwurf erst auf Knopfdruck (Chromium, headless) |
| UI | `Projektdetail: Arbeitspakete und Bugs` | vorhanden und automatisiert geprüft | `bin/vibe-web.py` `ticketCard`/`ticketFormCard`/`bugFormCard`; `tests/browser/test_tickets_ui.py` legt ein Arbeitspaket an, bearbeitet und löscht es und meldet einen Bug mit Kennzeichnung in der Feedback-Liste (Chromium, headless); Screenshot `docs/features/F15-arbeitspakete.png` |
| UI | `Sprache der Oberfläche (AP21)` | vorhanden und automatisiert geprüft | `bin/web/i18n.js` (Wörterbücher `en`/`de`, API `available()/current()/set()/t()/locale()`), `index.html` lädt i18n.js vor app.js; sichtbare UI-Strings in `app.js` laufen über `tr()` (Wörterbücher mit vollständigen en/de-Einträgen); Sprachwahl ist **global** auf einer neuen Navigationsseite Settings (`select[aria-label="Language"]`), serverseitig in `ui.json` (`GET/POST /api/language`, Default `en`), `<html lang>`+Meta `vibe-language` bei `GET /`; die V1-Projekt-Sprachschalter wurden entfernt; `scripts/setup-vibe.py` liefert `bin/web/i18n.js` (Installation-Lücke); Render-Renn-Schutz für asynchrone globale Renderer. Bekannte Backend-Meldungen/Sitzungszustände/Doctor-Labels werden clientseitig über `STATE_LABELS`/`DOCTOR_LABELS`/`MESSAGE_MAP`/`MESSAGE_PHRASES` übersetzt, Freitexte (Protokolle, Projektnamen) bleiben unangetastet. `tests/unit/test_ap21_i18n.py` (29 Fälle) und `tests/browser/test_ap21_i18n_ui.py` (25 Fälle) grün (Chromium, headless, isoliertes Dashboard). Siehe `docs/features/AP21.md`. |

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
| Bazzite-Startmenü | vorhanden und manuell geprüft | Starter, Desktopdatei, Icon, Installer und Uninstaller unter `scripts/`; echter Host-Test mit Container aus/an, Doppelklick, Tokenwechsel und Sonderzeichen (V-017) |
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
| Desktopdatei und Startmenü-Installer | `scripts/vibe-desktop.py`, `scripts/install-vibe-desktop.sh`, V-017 | Vorhanden; Installation nach `$XDG_DATA_HOME`, Sicherung fremder Einträge, Uninstall nur unveränderter Dateien |
| Icon `vibe.svg` | `scripts/vibe.svg`, V-017 | Im Repository und wird mitinstalliert |
| `vibe-launcher.sh` | `scripts/vibe_starter.py`, V-017 | Ersetzt den alten Launcher; prüft Health, startet Container/Dashboard bei Bedarf und öffnet den Browser |
| `vibe-secrets.sh`, `_secrets.env` | nur in der aktiven Installation | Geheimnisbereitstellung nicht reproduzierbar; absichtlich nicht importiert |
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
- Fehlt: reproduzierbare Installation/Rollback,
  Projektprüfung und automatisierte App-Tests.

Damit ist V-001 eine ehrliche Ausgangsbasis: Der Bestand ist versioniert und
gegen Veränderung abgesichert, aber **keine** Funktion gilt als vollständig
abgenommen.

## 14. Dokumentation

- Fachliche und technische Dokumentation: `docs/features/V-001.md`.
- Trilium: `vibe` → `Features` → `V-001 Bestandsaufnahme und Absicherung`
  (Notiz-ID `eMU1JVlKt1n5`); Zuordnung in `docs/trilium-index.md`.
