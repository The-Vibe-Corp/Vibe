# AP1 — opencode-go in der Sandbox und Schreibrechte des privaten Servers

Stand: 2026-11-20
Ticket: TICKETS.md AP1 („Fix bugs preventing opencode-go models from being available in sandbox, and sandbox write permissions“)
Ursprünglicher Arbeitsbranch: `feature/korbat-vibe-dev-bot/ap1-3`
Ursprünglicher Basiscommit: `1de016b`
Revalidierungsbranch: `feature/korbat/ap1`
Revalidierungsbasis: `8f26a85` (AP1 bereits durch Squash-Commit `976228b` enthalten)
Nachweis (Commit/Test): siehe TICKETS.md, Eintrag AP1.

## Ziel

Zwei im Ticket beschriebene Fehler beheben:

1. Der private `opencode serve`-Prozess schreibt nur in das Verzeichnis, für das
   er gestartet wurde. Wird er von der Preflight-Assistenz in `$P` gestartet,
   durfte das anschließende Paket in `$WT` nicht schreiben; dasselbe galt für
   den Wechsel von AP1 zu AP2.
2. In der Sandbox fehlten die `opencode-go`-Modelle, weil die Zugangsdaten in
   `~/.local/share/opencode/opencode.db` liegen, die Sandbox aber nur die
   Legacy-Datei `auth.json` kannte und `XDG_DATA_HOME` auf ein leeres
   Sandbox-Verzeichnis umstellte.

Die Schreibgrenze der Sandbox und die Trennung der Sitzungsdaten pro
Integrationsprojekt bleiben dabei erhalten.

## Ursachen mit Dateibezug

### Bug 1 — falsches write-dir des wiederverwendeten Servers

`bin/vibe-run.sh` schrieb in `private_server_file_write` nur `url`, `port` und
`password_file` nach `<log>.server.json`. `private_server_healthy` prüfte allein
die HTTP-Gesundheit unter dieser URL. `ensure_private_server` übernahm einen
solchen Server ohne zu prüfen, für welches Verzeichnis er läuft. Die
Preflight-Assistenz ruft `run_agent_in "$P"`, das Paket danach
`run_agent_in "$WT"` (beide in `bin/vibe-run.sh`). Der erste Server blieb
deshalb mit `--chdir "$P" --bind "$P" "$P"` aus `start_private_server` aktiv;
der Client in der neuen bwrap-Hülle konnte nur HTTP sprechen und erbte nicht
dessen Mount-Namespace.

### Bug 2 — Zugangsdaten nur in der Host-DB

`bin/vibe_sandbox.py` band in `bwrap_argv` ausschließlich
`~/.local/share/opencode/auth.json` ein. Diese Datei existiert in der
betroffenen Installation nicht; die Zugangsdaten (unter anderem der
`opencode-go`-Eintrag) stehen in der Tabelle `credential` der
`opencode.db`. Weil dieselbe Funktion `XDG_DATA_HOME=<state>/data` setzt,
legte der sandboxed Server eine leere eigene DB an und sah keinen Token.

## Fachliche Rückfrage und Entscheidung

Die Rückfrage `qace263c176a1` bot zwei Wege an; der Nutzer hat **A: Kopie nur
der Zugangsdaten** gewählt. Es wurde keine neue Rückfrage gestellt.

| Weg | Vorteile | Nachteile |
|---|---|---|
| A — Kopie nur der Zugangsdaten bei Sandbox-Erzeugung (gewählt) | Die bestehende Schreibgrenze bleibt unverändert. Host-DB und Sitzungen anderer Projekte werden nicht beschrieben. Es entstehen keine doppelten Sitzungs-Logs je Arbeitskopie; Sitzungen bleiben im Zustandsordner des Integrationsprojekts. Die kopierte DB enthält keine fremden Sitzungsverläufe; sie werden nicht in gemeinsame Dateien geschrieben. | Der kopierte Token ist eine Momentaufnahme; eine Rotation auf dem Host wird erst bei der nächsten Vorbereitung bzw. im Upgrade-Pfad übernommen. Die Quelle wird mit `immutable=1` gelesen; Änderungen, die zum Lesezeitpunkt nur im WAL liegen, werden nicht gesehen. |
| B — eine für alle Projekte gemeinsame, beschreibbare Host-DB | Zugangsdaten wären immer aktuell und müssten nicht kopiert werden. | Alle Projekte und Agenten teilen sich Sitzungen, Nachrichten und Tool-Zustand; sie könnten sich gegenseitig lesen und überschreiben. Die Schreibgrenze der Sandbox würde für die DB aufgegeben; parallele Läufe würden konkurrierende Schreibzugriffe auf eine Datei ausüben. Entspricht nicht der Antwort des Nutzers. |

## Umsetzung

### Bug 1 — Server an sein Zielverzeichnis binden

- `private_server_file_write` schreibt zusätzlich `write_dir` mit dem
  `os.path.realpath` von `$dir`. `url`, `port` und `password_file` bleiben
  unverändert.
- `private_server_healthy "$dir"` gibt nur 0 zurück, wenn die gesunde
  HTTP-Antwort zur Server-URL passt **und** das gespeicherte `write_dir`
  (realpath-Vergleich) zum übergebenen Verzeichnis passt. Fehlt `write_dir`
  in einer alten Serverdatei, gilt der Server als nicht passend.
- `ensure_private_server "$dir"` ruft `private_server_healthy "$dir"`. Bei
  Abweichung folgen `stop_private_server` + `start_private_server "$dir"`;
  danach wird die neue URL an `opencode run` übergeben.
- Das Sandbox-Projektargument bleibt ausdrücklich `"$P"` in
  `start_private_server` und `run_agent_in`; nur `--chdir` und `--write-dir`
  wechseln mit `$dir`.

### Bug 2 — Zugangsdaten in die Sandbox-DB

`bin/vibe_sandbox.py` bereitet in `bwrap_argv` nach dem Anlegen von
`data_home` die Datei `<state>/data/opencode/opencode.db` vor, bevor die
bwrap-Argumentliste gebaut wird:

- Quelle ist `$XDG_DATA_HOME/opencode/opencode.db`, sonst
  `~/.local/share/opencode/opencode.db` — jeweils in der Host-Sicht vor dem
  Setzen des Sandbox-`XDG_DATA_HOME`.
- Die Quelle wird nur lesend mit `mode=ro&immutable=1` geöffnet; `mode=ro`
  allein scheitert in dieser Umgebung.
- Das Schema stammt aus allen `sqlite_master`-Einträgen mit nichtleerem SQL,
  Tabellen zuerst, dann Indizes. `sqlite_autoindex_*` entsteht automatisch.
  Zeilen werden nur aus den vorhandenen Tabellen `credential`, `account`,
  `account_state`, `control_account` und `migration` übernommen. Es gibt
  keine Sitzungen, Nachrichten, Blobs oder kv-Modellkatalog-Einträge.
- Eine neue Zieldatei wird über eine Tempdatei und `os.replace` atomar
  angelegt (Modus 0600).
- Die Legacy-Bindung `--ro-bind <auth.json> <data>/opencode/auth.json` bleibt
  unverändert; der Modul-Docstring beschreibt die neue DB-Vorbereitung.

## Sicherheit, Ablage und Upgrade

### Sicherheit

- Die Host-DB wird nie beschrieben; sie wird mit einer nur-lesenden SQLite-URI
  geöffnet. Die Kopie liegt im beschreibbaren Sandbox-Zustandsordner, nicht im
  Projekt und nicht im Integrations-Repository.
- Es werden ausschließlich Zugangsdatentabellen befüllt; Sitzungs- und
  Nachrichtentabellen bleiben in der Kopie leer. Eine sandbox-lokale DB
  enthält damit keine Sitzungshistorie anderer Projekte.
- Die Sandbox ist weiterhin eine Schreibgrenze, keine Lesegrenze: Ein Agent
  konnte bereits vor AP1 die Host-DB lesen; durch die Kopie kommt keine neue
  Leseberechtigung hinzu.
- Fehler beim Kopieren führen zu einer verständlichen Warnung auf stderr; die
  Sandbox läuft ohne die zusätzlichen Zugangsdaten weiter. Warnungen enthalten
  keine Token-Werte.

### Wo Sitzungen und Logs liegen

- Sandbox-Zustand, opencode-DB und deren WAL/SHM-Dateien liegen unter
  `state_dir($P)` (SHA-256-Präfix des **Integrationsprojekts**; bei zu langem
  Pfad die kurze tmpfs-Wurzel). `TMPDIR` ist `state_dir($P)/tmp`.
- Weil das Sandbox-Projektargument `$P` bleibt, nutzen alle Arbeitskopien
  denselben Zustandsordner; es entstehen keine doppelten Sitzungs-Logs je
  Arbeitskopie.
- Der private Server protokolliert unter `$RUNTIME/<name>.log.server.log`,
  seine Übergabedatei ist `$RUNTIME/<name>.log.server.json`, der Läufer schreibt
  nach `$RUNTIME/<name>.log`. Die Serverdatei wird beim Laufende entfernt.
- `write_dir` in der Serverdatei nennt den realen Zielpfad (`$P` oder `$WT`)
  des jeweils laufenden Serverprozesses.

### Upgrade-Verhalten

- Hat die vorhandene Sandbox-DB schon `credential`-Zeilen, wird die Datei nicht
  angefasst (auch nicht bei einer Token-Rotation auf dem Host).
- Ist `credential` leer, werden die Zugangszeilen aus der Host-DB in einer
  Transaktion nachgezogen; vorhandene Sitzungen, Nachrichten und der
  kv-Katalog bleiben unberührt. Fehlende Zugangstabellen werden aus dem
  Quellschema ergänzt.
- Fehlt die Host-DB, entsteht keine Zieldatei und die Sandbox läuft weiter.
- Hat die Quelle keine `credential`-Tabelle, gibt es ebenfalls keinen Abbruch;
  es werden keine Zugangszeilen eingefügt.

## Tests

### Rot — vor der Umsetzung

```
$ python3 -m unittest tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest -v
Ran 1 test ...
FAILED (failures=1)
AssertionError: 2 != 1 : Es wurden nicht zwei Server gestartet (einer je Zielverzeichnis):
[{'event': 'listening', 'port_bound': 34653, 'pid': 646,
  'cwd': '.../proj', ...}, ...]
```
Der einzige Server lief mit `cwd=$P`; der Paketversuch in `$WT` wurde nicht
berücksichtigt.

```
$ python3 -m unittest tests.unit.test_ap1_sandbox_credentials -v
Ran 6 tests ...
FAILED (failures=2)
FAIL: test_ak1_schema_and_credentials_are_copied_without_session_data
AssertionError: False is not true : Sandbox-DB wurde nicht angelegt
FAIL: test_ak3_empty_credentials_are_filled_without_touching_sessions
AssertionError: Lists differ: [('opencode-go', 'test-token')] != []
```
AK2, AK4, AK5 und AK6 waren schon vor der Änderung grün (sie schützen die
Randfälle: vorhandene Daten unverändert lassen, kein Abbruch, alte Quelle,
unveränderte auth.json-Bindung).

### Grün — nach der Umsetzung

```
$ python3 -m unittest tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest -v
Ran 1 test ... OK

$ python3 -m unittest tests.unit.test_ap1_sandbox_credentials -v
Ran 6 tests ... OK
```
Der neue Läufer-Test sieht zwei `listening`-Ereignisse (erst `cwd=$P`, später
`cwd=$WT` aus der Versuch-Zeile) mit einem `term` dazwischen. AK1–AK6 prüfen
Schema und Zeilenkopie, 0 Sitzungszeilen, Unverändertheit einer DB mit
Zugangsdaten, den Upgrade-Pfad, fehlende/alte Quellen und die unveränderte
`auth.json`-Bindung.

Weitere tatsächlich ausgeführte Prüfungen:

- `bash -n bin/vibe-run.sh` → Exit 0.
- `python3 -m unittest tests.unit.test_b17_sandbox_argv -v` → 4/4 OK.
- `python3 -m unittest tests.unit.test_b17_sandbox_argv tests.unit.test_import_manifest -v` → 12/12 OK.
- `python3 scripts/check-import-manifest.py` → `OK: 58 Dateien stimmen mit docs/import-manifest.json überein.`, Exit 0.
- `python3 scripts/check-syntax.py` → `OK: 194 Python-, 8 Bash- und 3 JSON-Datei(en) syntaktisch geprüft.`, Exit 0.
- `python3 scripts/check-no-secrets.py` → `OK: keine Geheimnisse erkannt.`, Exit 0.
- `python3 -m unittest tests.unit.test_b13_private_server_runner -v` → 10 Tests, 9 OK, 1 Failure (`SandboxPrivateServerTest`, siehe Grenzen).
- `python3 -m unittest tests.unit.test_b13_private_server_runner tests.unit.test_ap1_sandbox_credentials tests.unit.test_b17_sandbox_argv -v` → 20 Tests, 19 OK, 1 Failure (dasselbe bwrap-Problem). Alle sieben AP1-Zeilen sind `ok`.

## Grenzen

- `bwrap` ist in dieser Umgebung nicht ausführbar: `bwrap: No permissions to
  create a new namespace, likely because the kernel does not allow
  non-privileged user namespaces.` Deshalb scheitert der bestehende
  `SandboxPrivateServerTest` unverändert an der Sandbox-Probe; der echte
  bwrap-Lauf mit kopierter DB konnte hier nicht verifiziert werden. Die
  DB-Vorbereitung wird ohne bwrap über die Attrappe `VIBE_BWRAP` geprüft.
- `immutable=1` liest die Host-DB als Momentaufnahme der Hauptdatei. WAL-Inhalte
  werden nicht übernommen; eine Token-Rotation während des Laufs wird nicht
  live nachgezogen. Eine bereits mit Zugangsdaten gefüllte Sandbox-DB wird
  grundsätzlich nicht überschrieben.
- Die Session-DB bleibt pro Integrationsprojekt; das vermeidet doppelte Logs,
  bedeutet aber auch, dass Projekte weiterhin getrennte Sitzungshistorien
  haben (gewollt entsprechend Antwort A).
- Für nicht-sandboxierte Läufe mit Kennwortdatei wird `write_dir` ebenfalls in
  die Serverdatei geschrieben und beim Zielwechsel neu gestartet; die
  Dateisystem-Schreibgrenze kommt dort weiterhin vom Prozess selbst, nicht
  von AP1.

## Revalidierung im Paketlauf `feature/korbat/ap1`

Der Paketlauf begann auf `8f26a85`; die technische AP1-Umsetzung war bereits
über den Squash-Commit `976228b` in der Basis enthalten. Zwischen `976228b`
und dieser Basis änderten sich weder `bin/vibe-run.sh` noch
`bin/vibe_sandbox.py` noch die AP1-Testdateien. Deshalb erfolgte keine
erneute, inhaltsgleiche Codeänderung. Dieser Paketstand ergänzt nur die
erneute unabhängige Prüfung und deren Nachweise.

### Erneut ausgeführte Fokus- und Pflichtprüfungen

Folgende Prüfungen wurden auf dem Revalidierungsstand tatsächlich ausgeführt:

- `python3 -m unittest tests.unit.test_ap1_sandbox_credentials -v`:
  **6/6 Tests OK**.
- `python3 -m unittest
  tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest -v`:
  **1/1 Test OK**; zwei Serverstarts mit Wechsel `$P` → `$WT` und Stop dazwischen.
- `python3 -m unittest tests.unit.test_b17_sandbox_argv -v`: **4/4 Tests OK**.
- `python3 -m unittest tests.unit.test_ap1_sandbox_credentials
  tests.unit.test_b13_private_server_runner tests.unit.test_b17_sandbox_argv -v`:
  **19/20 Tests OK**. Der einzige Fehlschlag bleibt der oben genannte reale
  bwrap-Test wegen fehlender Kernelberechtigung für User-Namespaces; die
  übrigen neun B13-Tests, sechs AP1-DB-Tests und vier Sandbox-Argv-Tests
  bestehen.
- `env -u SANDBOX bash scripts/verify.sh quick --project <Worktree>`: **Exit 0**;
  Manifest (58 Dateien), Syntax (195 Python-, 8 Bash-, 3 JSON-Dateien) und
  Secret-Check bestanden.
- `env -u SANDBOX bash scripts/verify.sh package --project <Worktree>`:
  **Exit 0**, **11/11 Tests OK**.

Für diese Prüfmodi liegt nur im isolierten Projekt-Worktree eine ignorierte
`.vibe/project.env` mit echten Prüfbefehlen. Die Produktivkonfiguration und der
Integrationsstand blieben unverändert.

`env -u SANDBOX bash scripts/verify.sh full --project <Worktree>` wurde gestartet,
aber der Tool-/Verify-Prozess wurde mit SIGTERM (Exit 143) getrennt. Der verwaiste
parallele Testläufer wurde kontrolliert beendet; die Logdatei enthielt nur den
Prüfkopf. **Kein abgeschlossener Volltest und keine vollständig grüne Suite
werden behauptet.** Ein versehentlich zusätzlich gestarteter zweiter
Verify-Prozess wurde sofort kontrolliert beendet (SIGTERM, Exit 143); die
isolierten Prüfumgebungen und deren OpenCode-Dienste wurden aufgeräumt. Gemäß
der ausdrücklichen Nutzeranweisung „Lauf war schon durch … einfach beenden“
wurde kein erneuter Volltest gestartet.

Die unabhängige Test-Agenten-Reproduktion der AP1-Fokusfälle steht in
`docs/reviews/AP1-test-agent-report.md`. Die produktiven Dateien sind gegenüber
dem ursprünglichen unabhängigen Review `docs/reviews/AP1-review-1.md` unverändert;
das erneute Review des revalidierten Bestands steht in
`docs/reviews/AP1-review-2.md`.

### DB-Entscheidung und Grenzen dieser Runde

Die Rückfrage `qace263c176a1` und die Antwort des Nutzers vom 20.11.2026 wurden
direkt aus dem Laufzeitbestand verifiziert. Die Entscheidung bleibt **A: Kopie
nur der Zugangsdaten**. Die genannten Vor-/Nachteile, der Ablageort und die
Sicherheitsgrenzen oben gelten unverändert. Da sich die Faktenlage nicht
geändert hat, wurde keine zweite DB-Rückfrage gestellt.

Ein auth-only Refresh nach Token-Rotation ist als mögliche spätere Verbesserung
denkbar, aber kein neuer AP1-Defekt: Das Nichtüberschreiben bestehender
Zugangsdaten ist ausdrücklich durch AK2 und die ursprüngliche Entscheidung
festgelegt. Diese Grenze wird nicht durch eine nicht abgestimmte Änderung des
Persistenzmodells umgangen.

### Externe Abschlussgrenzen

Die Projektregeln verlangen grundsätzlich eine verifizierte
Trilium-Dokumentation. In dieser Sitzung meldet `opencode mcp list`
**„No MCP servers configured“**, und die verfügbare MCP-Ressourcenabfrage ist
leer. Auf die daraufhin gestellte Abschlussrückfrage `qfc1fe3f5fc77` wählte der
Nutzer ausdrücklich die **lokale Ausnahme ohne Trilium/Push/PR und ohne
Integrationsmerge**. Auf die komplementäre Rückfrage `q419e128a8b14`
präzisierte er: **„Trilium nicht benötigt, Lauf war schon durch. Wenn alles
passt, einfach beenden.“** Deshalb wird in diesem Folgelauf weder eine
Trilium-Synchronisation noch ein GitHub-/Integrationsvorgang ausgeführt; die
lokalen Paketkriterien sind maßgeblich.
