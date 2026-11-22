# B4 — Unabhängiger Test-Agent: Bericht

Arbeitspaket: B4 „Install fails with error" (FEEDBACK.md).
Arbeitskopie/Branch: `feature/korbat/b4`, Ausgangscommit `578a6dd`.
Neue Testdatei: `tests/unit/test_b4_install_empty_runs.py` (16 Fälle, eigenes
Laden von `scripts/setup-vibe.py` über `SourceFileLoader("setup_vibe_b4", …)`).

Testbefehl (vom Coding-Agenten vorgesehen und hier tatsächlich ausgeführt):

```
python3 -m unittest tests.unit.test_b4_install_empty_runs -v
```

Es wurden **keine** Produktionsdateien, keine bestehenden Tests, keine
Konfiguration und keine Geheimnisse geändert. `git status` zeigt nur die neue
Testdatei (und diesen Bericht). Alle schreibenden Zugriffe der Tests liegen in
`tempfile`-Verzeichnissen; es wird kein echtes `HOME`/`VIBE_*`, keine
produktive Installation, kein Netz und kein echtes tmux verwendet.

## 1. Abgeleitete Testfälle

Legende: V = Vorbedingung, A = Aktion, E = Erwartung, F = Fehlerfall.

### AK1 — vorhandene leere `runs.json` (0 Byte) sperrt nicht

| # | Testname | V / A / E / F |
|---|---|---|
| 1 | `EmptyRunStateDirectTest.test_empty_runs_file_is_not_a_block_reason` | V: Laufzeitordner mit vorhandener, 0-Byte-großer `runs.json`; kein tmux. A: `setup.running_installation(logs, which=lambda: None)`. E: `[]`. F: Sperrgrund „… ist nicht lesbar“ (der gemeldete B4-Fehler). |
| 2 | `UpdateWithEmptyRunsTest.test_update_runs_through_with_an_empty_runs_file` | V: bestehende temporäre Installation, `bin/vibe` = „ALT“, leere `_logs/runs.json`. A: `main(["--yes","--update","--vibe",…,"--install",toolchain,"--logs",logs])`. E: Exit 0, keine Zeile „wird gerade verwendet“, Programmdatei tatsächlich ersetzt. F: Exit 1 und unveränderte Installation. |

### AK2 — reiner Leerraum wird wie leer behandelt

| # | Testname | V / A / E / F |
|---|---|---|
| 3 | `EmptyRunStateDirectTest.test_whitespace_only_runs_file_is_not_a_block_reason` | V: `runs.json` enthält `"\n"` bzw. `"  \n\t \n"` (zwei `subTest`-Fälle). A: `running_installation`. E: jeweils `[]`. F: Leerraum löst `json.loads`-ValueError und damit eine Sperre aus. |
| 4 | `UpdateWithEmptyRunsTest.test_update_runs_through_with_a_whitespace_only_runs_file` | V: wie 2, aber `runs.json` = `"\n"`. A: `--yes --update`. E: Exit 0, Datei ersetzt. F: wie 2. |

### AK3 — nicht-leerer unlesbarer Inhalt sperrt weiterhin (Bestandsvertrag)

| # | Testname | V / A / E / F |
|---|---|---|
| 5 | `EmptyRunStateDirectTest.test_non_empty_unreadable_runs_file_remains_a_block_reason` | V: `runs.json` = `"{kein json"`. A: `running_installation`. E: genau ein Grund, enthält „ist nicht lesbar“ und den Pfad. F: defekter Bestand wird stillschweigend als leer gewertet. |
| 6 | `UpdateWithEmptyRunsTest.test_update_still_refuses_a_non_empty_unreadable_runs_file` | V: bestehende Installation, `bin/vibe` = „ALT“, `runs.json` = `"{kein json"`. A: `--yes --update`. E: Exit 1, „wird gerade verwendet“ + „nicht lesbar“, „ALT“ bleibt. F: konservative Sperre entfällt. |

### AK4 — Lesefehler (OSError) sperrt weiterhin

| # | Testname | V / A / E / F |
|---|---|---|
| 7 | `EmptyRunStateDirectTest.test_oserror_when_reading_the_runs_path_remains_a_block_reason` | V: `logs/runs.json` ist ein **Verzeichnis** (kein `chmod`, siehe §4). A: `running_installation`. E: genau ein Grund mit „ist nicht lesbar“ und Pfad. F: `IsADirectoryError` (OSError) wird als leer verschluckt. |
| 8 | `UpdateWithEmptyRunsTest.test_update_still_refuses_when_the_runs_path_is_unreadable` | V: wie 7 auf einer Installation; `bin/vibe` = „ALT“. A: `--yes --update`. E: Exit 1, „nicht lesbar“, „ALT“ bleibt. F: Lesefehler erlaubt eine Änderung der laufenden Installation. |

### AK5 — alle drei Guard-Nutzer: leer sperrt nicht, live sperrt weiter

| # | Testname | V / A / E / F |
|---|---|---|
| 9 | `UninstallWithEmptyRunsTest.test_uninstall_runs_through_with_an_empty_runs_file` | V: Installation, leere `_logs/runs.json`. A: `--yes --uninstall`. E: Exit 0, `bin/vibe` entfernt. F: Uninstall durch leeres Register blockiert. |
| 10 | `RollbackWithEmptyRunsTest.test_rollback_runs_through_with_an_empty_runs_file` | V: zwei Installationen (Backup vorhanden), `bin/vibe` = „ALT“ im Backup, danach leere `runs.json`. A: `--yes --rollback`. E: Exit 0, „Rollback“, „ALT“ wiederhergestellt. F: Rollback durch leeres Register blockiert. |
| 11 | `UninstallWithEmptyRunsTest.test_uninstall_still_refuses_a_running_run_with_live_session` | V: `runs.json` mit `running` + existierender tmux-Sitzung (Fake-tmux). A: `--yes --uninstall`. E: Exit 1, „wird gerade verwendet“, Programmdatei bleibt. F: Uninstall ignoriert einen echten Lauf. |
| 12 | `RollbackWithEmptyRunsTest.test_rollback_still_refuses_a_running_run_with_live_session` | V: wie 11, Backup vorhanden. A: `--yes --rollback`. E: Exit 1, nicht „ALT“, Lauf-ID im Grund. F: Rollback ignoriert einen echten Lauf. |

### AK6 — Live-Sperre bleibt vollständig erhalten

| # | Testname | V / A / E / F |
|---|---|---|
| 13 | `EmptyRunStateDirectTest.test_live_run_with_existing_session_remains_a_block_reason` | V: `running`-Eintrag, `session` existiert laut Fake-tmux. A: `running_installation`. E: Grund nennt Lauf-ID und `running`. F: Live-Erkennung bricht. |
| 14 | `UpdateWithEmptyRunsTest.test_update_still_refuses_a_running_run_with_live_session` | V: bestehende Installation, `running` + existierende Sitzung. A: `--yes --update`. E: Exit 1, „wird gerade verwendet“, „lauf-live“, „ALT“ bleibt. F: Update über einen laufenden Agenten. |
| 15 | `UpdateWithEmptyRunsTest.test_update_still_refuses_a_starting_run_with_live_session` | V: wie 14, Zustand `starting`. A: `--yes --update`. E: Exit 1, „lauf-start“, „ALT“ bleibt. F: `starting` wird nicht mehr als live erkannt. |

### Schutzwache aus dem Bestandsvertrag

| # | Testname | V / A / E / F |
|---|---|---|
| 16 | `EmptyRunStateDirectTest.test_missing_runs_file_is_not_a_block_reason` | V: keine `runs.json`. A: `running_installation`. E: `[]`. F: Änderung würde das bisherige „fehlt = leer“-Verhalten brechen. |

## 2. Rotphase am Ausgangsstand (unverändert)

Befehl/Ergebnis:

```
$ python3 -m unittest tests.unit.test_b4_install_empty_runs -v
...
Ran 16 tests in 0.157s

FAILED (failures=7)
exit code 1
```

Rot sind genau die Fälle, die den B4-Defekt belegen:

```
FAIL: test_empty_runs_file_is_not_a_block_reason
FAIL: test_whitespace_only_runs_file_is_not_a_block_reason (content='\n')
FAIL: test_whitespace_only_runs_file_is_not_a_block_reason (content='  \n\t \n')
FAIL: test_rollback_runs_through_with_an_empty_runs_file
FAIL: test_uninstall_runs_through_with_an_empty_runs_file
FAIL: test_update_runs_through_with_a_whitespace_only_runs_file
FAIL: test_update_runs_through_with_an_empty_runs_file
```

Beobachtete Originalausgaben (nicht erfunden):

```
test_empty_runs_file_is_not_a_block_reason
AssertionError: Lists differ: [] != ['Laufzustand /tmp/.../logs/runs.json ist nicht lesbar']

test_update_runs_through_with_an_empty_runs_file
AssertionError: 0 != 1 : vibe-Setup
...
FEHLER: Die Installation wird gerade verwendet; nichts geändert.
  - Laufzustand /tmp/.../Vibe/_logs/runs.json ist nicht lesbar
Beende die Läufe/Sitzungen oder nutze --force für eine bewusste Aktualisierung.

test_uninstall_runs_through_with_an_empty_runs_file
FEHLER: Die Installation wird gerade verwendet; nichts entfernt.

test_rollback_runs_through_with_an_empty_runs_file
FEHLER: Die Installation wird gerade verwendet; nichts zurückgerollt.
```

Bereits grün (Schutzwachen, wie beabsichtigt 9/16): fehlende Datei,
AK3 direkt und als Update, AK4 direkt und als Update, AK5-Uninstall-Live,
AK5-Rollback-Live, AK6 direkt und als Update (`running` und `starting`).

Damit ist der Fehler unabhängig bestätigt: Eine vorhandene, aber leere (bzw.
nur Leerraum enthaltende) `runs.json` erzeugt über `json.loads("")` einen
`ValueError`, der als „Laufzustand … ist nicht lesbar“ jede Aktualisierung,
Deinstallation und jeden Rollback blockiert.

### Erreichbarkeit der Erwartungen geprüft (ohne Produktionsänderung)

Um auszuschließen, dass die Assertions unerfüllbar sind, wurde die geladene
`scripts/setup-vibe.py` **nur im Speicher** eines Wegwerf-Interpreters so
gepatcht, dass eine leere/nur-Leerraum-Datei beim Guard wie „fehlt“ behandelt
wird. Ergebnis: `Ran 16 tests … OK`. Das ist **kein** Implementierungsnachweis,
sondern nur der Beleg, dass die Testfälle mit der intendierten Semantik
erfüllbar sind. Der echte Grünnachweis erfolgt nach der Implementierung mit
dem obigen Befehl.

## 3. Baseline der Bestandsregression

```
$ python3 -m unittest tests.unit.test_install_lifecycle -v
Ran 43 tests in 0.442s

FAILED (failures=7, errors=28)
exit code 1
```

Die Datei ist am Ausgangsstand **nicht** grün; 35 von 43 Fällen sind rot.
Das ist die bereits dokumentierte B17-Baseline (docs/features/AP3-Korbat.md:
„`test_install_lifecycle`: 7/28“, also 7 Failures und 28 Errors). Ursache ist
nicht B4, sondern der historische Harness: `InstallLifecycleBase.install()`
ruft `setup.install_program_files(kit, self.vibe, …)` auf, während
`install_program_files` (und `main()` mit `--install`) das **Toolchain**-
Verzeichnis als Ziel erwartet; deshalb entsteht `/…/Vibe/bin` statt
`/…/Vibe/_toolchain/bin`. Die neuen B4-Tests übernehmen das Muster des
Harness (`run_main`, bereinigte Umgebung, `make_kit`), rufen `install()` aber
korrekt mit `self.toolchain` auf. Die Rotphase der B4-Tests ist daher nicht von
dieser Baseline verfälscht.

**Hinweis:** Die Bestandsdatei `tests/unit/test_install_lifecycle.py` darf vom
Coding-Agenten nicht angefasst, abgeschwächt oder „repariert“ werden; ihre
B17-Baseline ist nicht Teil von B4.

## 4. Simulationsentscheidungen und Grenzen

- **AK4/OSError:** Statt `chmod` (auf FUSE/NTFS wirkungslos) wird
  `runs.json` als **Verzeichnis** angelegt. `Path.read_text()` wirft dann
  `IsADirectoryError`, eine echte `OSError`-Unterklasse; damit wird genau der
  `except OSError`-Zweig des Guards geprüft.
- **tmux:** Es gibt keinen echten tmux-Aufruf. Die Sitzungsprüfung wird über
  injizierte `which`/`runner`-Callables gesteuert (Muster aus
  `RunningGuardTest.tmux_check`); nur die genannte Sitzung gilt als vorhanden.
- **Isolation:** `HOME` und `--install`/`--logs` zeigen auf `tempfile`-Pfade;
  `VIBE_INSTALL` ist nicht gesetzt, sodass der B17-Quellenschutz nicht
  eingreift. Keine Netz-, Modell- oder GitHub-Aufrufe.
- **Nicht geprüft:** echtes tmux, echte Rotation (`runs.json.1`), Rechte-
  fehler über Dateisystemrechte sowie das Verhalten des echten
  Installationsskripts unter root/`update.sh`. Für B4 ist der Guard-Vertrag
  maßgeblich; die genannten Punkte sind außerhalb des Testumfangs.

## 5. Hinweise für den Coding-Agenten

1. Kleinste Änderung in `running_installation()`: leere bzw. nur aus
   Leerraum bestehende `runs.json` wie „Datei fehlt“ behandeln
   (`text.strip()` bzw. `if not text.strip(): data = None`). `json.loads("")`
   darf nicht mehr als Lesefehler gelten.
2. `except (OSError, ValueError)` muss für **nicht-leeren** unlesbaren Inhalt
   und für echte Lesefehler erhalten bleiben (Fälle 5–8).
3. Die Live-Erkennung (Zustände `running`/`starting`, `session_state`,
   konservatives Verhalten ohne prüfbare Sitzung) nicht verändern
   (Fälle 11–15).
4. `tests/unit/test_b4_install_empty_runs.py` und
   `tests/unit/test_install_lifecycle.py` nicht ändern oder abschwächen.
5. Nach der Implementierung denselben Befehl erneut ausführen und das
   Ergebnis (16/16 OK erwartet) melden.

## 6. Status

- Testdatei: `tests/unit/test_b4_install_empty_runs.py`, 16 Fälle.
- Rotphase am Ausgangsstand: 7 rot (AK1, AK2, AK5), 9 Schutzwachen grün,
  Exit 1.
- Baseline `test_install_lifecycle`: 43 Fälle, 7 Failures/28 Errors
  (dokumentierte B17-Baseline, nicht B4).
- Grünphase nach Implementierung: offen; Assertions werden nicht
  abgeschwächt.
