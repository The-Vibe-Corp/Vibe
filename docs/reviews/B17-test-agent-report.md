# B17 Test-Agent-Bericht

Arbeitspaket: **B17 — Entwicklung und Verifikation dürfen die laufende Instanz nicht verändern**
Branch: `vibe/vibe-B17-1795080213297950373-57043-2223`
Datum: 19.11.2026
Rolle: unabhängiger Test-Agent (keine Produktionscode-Änderung, kein Commit, kein Branchwechsel)

## 1. Auftrag und Ergebnis

Ziel war, die Abnahmefälle für B17 **vor** der Implementierung zu schreiben, die
Rotphase zu belegen und die Fälle fachlich zu dokumentieren. Das ist erledigt:

- Ursprünglich 24 neue Testfälle in vier Dateien, die ausschließlich unter
  `tempfile` arbeiten. Nach den Reviewrunden 1–3 umfassen dieselben vier Module
  jetzt **29 Tests** (Zählweise unten).
- Drei bestehende Setup-Testmodule wurden für die neue `environ=`-Schnittstelle
  und explizite Temp-Pfade angepasst (keine Abschwächung von Assertions).
- Rotphase je Anforderung mit Befehl und Auszug belegt (Abschnitt 5).
- Alle 29 Tests laufen auf dem aktuellen Stand grün; der Nachweis des zuletzt
  ergänzten Moduls steht in §5.8.5.
- Keine Produktionsdatei bleibt verändert (siehe 3.1), kein Commit erstellt.

Zählweise (Stand `c59de24`, Produktions- und Teststand wie `6eeb9a4`):
`test_b17_isolation` 12 + `test_b17_questions_runtime` 6 +
`test_b17_sandbox_argv` 4 + `test_b17_runner_isolation` 7 = **29**. Davon sind
24 die ursprünglichen Abnahmefälle (#1–#24) und 5 Zusatzfälle aus den
Reviewrunden: +2 in `test_b17_isolation` (§5.8.3), +2 in
`test_b17_questions_runtime` (§5.8.2/§5.8.5) und +1 in
`test_b17_runner_isolation` (§5.8.1).

## 2. Zuordnung der Anforderungen

Die Anforderungen aus `FEEDBACK.md` (B17) wurden in neun prüfbare Kriterien
zerlegt. Diese Nummerierung ist die Arbeitsnummerierung dieses Berichts.

| AK | Anforderung aus B17 | Prüfschwerpunkt | Testdatei |
|----|---------------------|-----------------|-----------|
| AK1 | `setup.main(..., environ=...)`; alle Pfade aus der übergebenen Umgebung | Pfadauflösung, Konfigurationspfad, Hinweistext | `tests/unit/test_b17_isolation.py` |
| AK2 | `--update` auf die laufende Instanz nur mit autorisierter Quelle | Guard, `--source`-Hinweis, `--dry-run`, `--reuse` | `tests/unit/test_b17_isolation.py` |
| AK3 | Klare Quelle `--source` | Quelle wird verwendet und in `version.json` vermerkt; unvollständige Quelle bricht ab | `tests/unit/test_b17_isolation.py` |
| AK4 | Tests übergeben bereinigte Umgebung und explizite Temp-Pfade | `--install`/`--logs` + `environ` in den Setup-Tests | `test_ap04_setup_harness.py`, `test_setup_vibe.py`, `test_install_lifecycle.py` |
| AK5 | Regressionstest: Test-`--update` schreibt nur Temp-Pfade | Byte-Snapshot des Fake-Produktivbereichs | `tests/unit/test_b17_isolation.py` |
| AK6 | Läufer startet Agenten ohne Produktivpfade | Prozessumgebung des Agenten | `tests/unit/test_b17_runner_isolation.py` |
| AK7 | Rückfragen des Agenten ohne Produktivpfad | Prompt-Hinweis und `vibe ask/answer --runtime` | `test_b17_runner_isolation.py`, `test_b17_questions_runtime.py` |
| AK8 | Sandbox gilt für Agent **und** Prüfungen | `bwrap`-Verdrahtung, Schreibverzeichnisse, bereinigte Verify-Umgebung | `test_b17_sandbox_argv.py`, `test_b17_runner_isolation.py` |
| AK9 | Ohne neue Angaben bleibt das bisherige Verhalten | unverändertes `bwrap_argv`-Standardverhalten | `tests/unit/test_b17_sandbox_argv.py` |

## 3. Sicherheitsregeln für die Ausführung

Die Tests dürfen niemals die produktive Umgebung erben. Jeder Lauf erfolgt
deshalb mit:

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest <modul> -v
```

Zusätzlich gilt:

- Die simuliert produktive Umgebung wird **nur** als `environ=` an
  `setup.main(...)` übergeben, nie per `os.environ`-Patch.
- Schreibende Tests arbeiten ausschließlich unter `tempfile.TemporaryDirectory`.
- Die drei Setup-Module dürfen **nicht** im unveränderten HEAD-Zustand laufen
  (sie rufen `setup.main` ohne `environ=` auf und würden die echte Installation
  treffen). Ihre Rotphase ist der erwartete `TypeError` vor jedem Schreibzugriff.
- `tests/unit/test_questions.py` und `tests/unit/test_sandbox.py` bleiben
  unverändert und dienen als Kontextanker.

### 3.1 Vorfall beim Baseline-Vergleich (transparent)

Für die Abgrenzung „pre-existing vs. B17" wurden Kopien der HEAD-Fassungen von
`test_setup_vibe.py` und `test_install_lifecycle.py` ausgeführt. Damit trat der
in B17 beschriebene Vorfall erneut auf: Die echte Konfiguration
`~/.config/vibe/config.json` und die echte Installation
`/home/vibe/vibe-toolchain` wurden aktualisiert (u. a. `harness.json` auf `pi`).
Das bestätigt die Notwendigkeit von B17 unmittelbar.

Der Zustand wurde vollständig zurückgesetzt:

- `~/.config/vibe/config.json` aus der ersten Sicherung des Laufs
  wiederhergestellt (MD5 `42f9a48e20…`, `prod.workspace=/home/vibe/VibeCode`).
- `/home/vibe/vibe-toolchain/harness.json` auf den Standard `opencode` gesetzt.
- Die vier vom Testlauf erzeugten `backup-20261119-1047*`-Ordner entfernt.
- Programmdateien und `version.json` waren inhaltlich unverändert; geprüft per
  Vergleich gegen die erste Sicherung.

Konsequenz: HEAD-Fassungen der drei Setup-Module werden nicht mehr ausgeführt.
Der Vergleich dient nur der Einordnung der Baseline (Abschnitt 6).

## 4. Testfälle

### 4.1 `tests/unit/test_b17_isolation.py` — Setup (AK1, AK2, AK3, AK5)

Fake-Produktivbereich: `<temp>/produktion` mit Home, Workspace
`<temp>/produktion/VibeCode`, Installation `<…>/_toolchain`, Laufzeit
`<temp>/produktion/runtime` und Konfiguration unter dem Fake-Home. Der
Prüfbereich `<temp>/pruefung` ist davon getrennt. `snapshot()` vergleicht
SHA-256 je Datei; zusätzlich darf im Fake-Produktivbereich keine
`backup-*`-Sicherung entstehen.

| # | Test | Vorbedingung | Aktion | Erwartetes Ergebnis | Fachliche Bedeutung |
|---|------|--------------|--------|---------------------|---------------------|
| 1 | `MainEnvironTest.test_dry_run_resolves_defaults_from_the_given_environ` | Leerer Prüfbereich; `environ` mit Home/Workspace/Install/Runtime | `main(["--yes","--dry-run"], environ=…)` | Exit 0; Ausgabe nennt Workspace, Install, Runtime und `<home>/.config/vibe/config.json`; nichts angelegt | AK1: `environ` ist die einzige Quelle der Pfadauflösung, auch für den Konfigurationspfad |
| 2 | `MainEnvironTest.test_closing_hint_reads_the_given_environ` | `environ.VIBE` zeigt auf ein anderes, nicht existierendes Verzeichnis | Installation mit explizitem `--vibe/--install/--logs` | Exit 0; Ausgabe enthält `Hinweis: VIBE=<anderes Verzeichnis>`; das andere Verzeichnis entsteht nicht | AK1: Warnungen vergleichen gegen `environ`, nicht gegen `os.environ` |
| 3 | `UpdateGuardTest.test_update_on_the_running_instance_is_refused_without_writes` | Fake-Installation vorhanden; `environ.VIBE_INSTALL` zeigt darauf; kein `--install` | `--update --yes …` mit neuem Workspace | Exit 1; Ausgabe nennt `--source`; Fake-Produktivbereich byte-identisch; neuer Workspace nicht angelegt | AK2: versehentliches Update der laufenden Instanz wird vor jedem Schreibzugriff verweigert |
| 4 | `UpdateGuardTest.test_dry_run_on_the_running_instance_is_allowed_and_explains_the_guard` | wie #3 | `--update --dry-run --yes` | Exit 0; Ausgabe nennt `--source`; keine Änderung | AK2: Vorschau bleibt gefahrlos möglich und erklärt die Autorisierung |
| 5 | `UpdateGuardTest.test_reuse_on_the_running_instance_is_not_blocked` | Fake-Installation mit `bin/vibe`, `harness.json`, `version.json`; Konfiguration passend | `--reuse --yes … --vibe <fake> --logs <fake>` | Exit 0; vorhandene Dateien unverändert; keine Sicherung; Konfiguration unverändert | AK2: Der Guard betrifft nur `--update`; Wiederverwenden ergänzt nur Fehlendes |
| 6 | `IsolatedUpdateTest.test_test_update_writes_only_into_the_temp_root` | Prüf-Installation `<temp>/toolchain` mit alter `bin/vibe`; Fake-Produktivbereich vorhanden | `--update --yes … --vibe/--install/--logs <temp>` mit bereinigtem `environ` | Exit 0; Programmdateien aktualisiert; `backup-*`, `version.json` und Konfiguration unter Temp; `version.json.source` = Kit; Fake-Produktivbereich byte-identisch | AK5: Regressionstest des Vorfalls — ein Test-Update schreibt ausschließlich Temp-Pfade |
| 7 | `IsolatedUpdateTest.test_environ_install_target_wins_without_a_cli_option` | `environ` mit `VIBE`, `VIBE_INSTALL`, `VIBE_RUNTIME`, Home | Installation ohne `--install`/`--logs` | Exit 0; Programmdateien im `environ`-Install; Konfiguration nennt Workspace/Install/Runtime aus `environ`; Default-Ziel `<home>/VibeCode/_toolchain` entsteht nicht | AK1: `VIBE_INSTALL`/`VIBE_RUNTIME` wirken aus `environ`, nicht aus der Prozessumgebung |
| 8 | `SourceOptionTest.test_update_with_an_explicit_source_updates_the_instance` | Fake-Installation; zweites Kit mit Version `9.9.9` | `--update … --source <kit>` | Exit 0; `version.json` hat Version `9.9.9` und `source` = aufgelöstes Kit | AK3: Nur die ausdrücklich benannte Quelle autorisiert das Update und wird nachvollziehbar vermerkt |
| 9 | `SourceOptionTest.test_source_with_a_broken_directory_changes_nothing` | Fake-Installation; leeres Quellverzeichnis | `--update … --source <leer>` | Exit 1; Ausgabe enthält `Unvollständiges Quellverzeichnis`; Fake-Produktivbereich unverändert | AK3: Eine unbrauchbare „autorisierte" Quelle darf nichts verändern |
| 10 | `SourceOptionTest.test_install_wrapper_names_its_own_source` | Repository | Datei `install-vibe.sh` lesen | Enthält `--source` und `"$KIT"` | AK3: Der Wrapper autorisiert seinen eigenen Checkout als Quelle |

Hinweis zu #3/#4: Der Guard setzt voraus, dass das Ziel implizit aus
`environ`/Konfiguration aufgelöst wird. Bei einem ausdrücklich übergebenen
`--install` darf er nicht greifen, sonst würden die bestehenden Update-Tests in
`test_ap04_setup_harness.py` und `test_install_lifecycle.py` blockiert (sie
arbeiten bewusst in Temp-Pfaden). Diese Auslegung ist in Abschnitt 7 als
Bestätigungspunkt vermerkt.

Testumfang des Moduls: 12 Tests — die Fälle #1–#10 plus die beiden
Guard-Fälle aus Review Runde 1 (`test_update_with_an_explicit_install_on_the_running_instance_is_refused`,
`test_update_with_an_explicit_install_and_source_is_allowed`, dokumentiert in
§5.8.3).

### 4.2 `tests/unit/test_b17_questions_runtime.py` — Rückfragen (AK7)

Geladen wird das echte `bin/vibe` als Modul. `VIBE_RUNTIME` und
`VIBE_CONFIG_FILE` zeigen auf getrennte Temp-Ordner; die Umgebung wird nach dem
Laden zurückgesetzt, sodass `LOGS` weiterhin auf den Umgebungspfad zeigt. Damit
ist belegbar, ob `--runtime` wirklich verwendet wird.

| # | Test | Vorbedingung | Aktion | Erwartetes Ergebnis | Fachliche Bedeutung |
|---|------|--------------|--------|---------------------|---------------------|
| 11 | `test_cmd_ask_writes_into_the_given_runtime` | `env-runtime` und `pruef-runtime` getrennt | `cmd_ask --runtime <pruef> --project "" --no-wait "Frage" --option Rot` | Genau eine Frage unter `<pruef>/questions`; unter `<env-runtime>/questions` nichts | AK7: Eine Rückfrage des Agenten landet im Laufzeitordner des Laufs, nicht im Produktivpfad |
| 12 | `test_cmd_answer_uses_the_given_runtime` | Frage unter `<pruef>` | `cmd_answer --runtime <pruef> <id> --option 1` | Antwort in `<pruef>` gespeichert; `<env-runtime>/questions` entsteht nicht | AK7: Antworten werden am selben ausdrücklichen Ort gelesen/geschrieben |
| 13 | `test_wait_reads_the_answer_from_the_given_runtime` | Frage unter `<pruef>` bereits beantwortet | `cmd_ask --runtime <pruef> --wait <id>` | Ausgabe enthält `Antwort`; `<pruef>/questions` existiert | AK7: `--wait` liest die Antwort aus dem angegebenen Laufzeitordner |
| 14 | `test_autonomous_mode_is_read_from_the_given_runtime` | Autonomiemodus unter `<pruef>` aktiviert | `cmd_ask --runtime <pruef> --wait <id>` | Ausgabe enthält `Autonomer Modus`; `is_enabled(<env-runtime>)` bleibt falsch | AK7: Die Autonomieentscheidung wird aus dem Laufzeitordner des Laufs gelesen |

Testumfang des Moduls: 6 Tests. Zusätzlich zu #11–#14 (die Nummern #1–#24
bezeichnen weiterhin die ursprünglichen Abnahmefälle) enthält das Modul zwei
Reviewfälle, die über ihre Testnamen geführt werden:

- `QuestionRuntimeTest.test_timeout_and_autonomous_hints_name_the_given_runtime`
  (Review 1/Medium, §5.8.2; von Review 2 um den `subTest` `hint='creation'`
  erweitert, §5.8.5) — Timeout-, Autonomie- und Erzeugungsmeldung nennen den
  übergebenen Laufzeitordner.
- `PackageHintRuntimeTest.test_preflight_and_barrier_hints_name_the_given_runtime`
  (Review 2, §5.8.5) — PREFLIGHT- und BARRIER-Hinweis nennen den übergebenen
  Laufzeitordner.

### 4.3 `tests/unit/test_b17_sandbox_argv.py` — Sandbox-Argumente (AK8, AK9)

Die Tests prüfen `vibe_sandbox.bwrap_argv` direkt; bubblewrap wird nicht
gestartet. `VIBE_BWRAP` zeigt auf eine ausführbare Attrappe.

| # | Test | Vorbedingung | Aktion | Erwartetes Ergebnis | Fachliche Bedeutung |
|---|------|--------------|--------|---------------------|---------------------|
| 15 | `test_extra_write_dirs_are_bound_writable` | Projekt mit `.vibe`; vorhandene Arbeitskopie | `bwrap_argv(project, ["true"], runtime=…, extra_write_dirs=[copy], chdir=copy)` | Enthält `("--bind", copy, copy)` | AK8: Die Paket-Arbeitskopie ist im Sandbox-Lauf beschreibbar |
| 16 | `test_chdir_overrides_the_working_directory` | wie #15 | wie #15 | `--chdir` = Arbeitskopie, nicht realpath(Projekt) | AK8: Der Agent arbeitet in der Arbeitskopie, auch wenn die Sandbox vom Konfigurationsprojekt aufgebaut wird |
| 17 | `test_question_folder_is_writable_and_autonomous_state_read_only` | Laufzeitordner mit `questions` | `bwrap_argv(project, ["true"], runtime=…)` | `--bind` für `<runtime>/questions`; `--ro-bind-try` für `<runtime>/autonomous.json`; autonom nie beschreibbar | AK7/AK8: Rückfragen funktionieren in der Sandbox; der Autonomiezustand ist nur lesbar |
| 18 | `test_without_new_arguments_the_previous_behaviour_stays` | Keine neuen Angaben, kein `VIBE_RUNTIME` | `bwrap_argv(project, ["true"])` | `--chdir` = realpath(Projekt); keine `questions`/`autonomous.json`-Bindung | AK9: Ohne neue Angaben bleibt das Verhalten unverändert |

Vertrag für die Implementierung: `bwrap_argv(project, command, bwrap=None,
runtime=None, extra_write_dirs=(), chdir=None)`. Die Namen `runtime` und
`bwrap` sind bestehend; `extra_write_dirs` und `chdir` sind die neuen
Parameter. Die CLI-Namen der Sandbox bleiben der Implementierung überlassen.

### 4.4 `tests/unit/test_b17_runner_isolation.py` — Läufer (AK6, AK7, AK8)

Der echte `bin/vibe-run.sh` läuft in einer Fake-Toolchain. Ein
aufzeichnender `opencode`-Wrapper schreibt `argv` und `env` als JSONL; ein
Fake-`bwrap` schreibt seine Argumente und führt den Befehl nach `--` aus.
`hide_vibe=True` erzeugt die Vorfall-Arbeitskopie ohne `.vibe`.

| # | Test | Vorbedingung | Aktion | Erwartetes Ergebnis | Fachliche Bedeutung |
|---|------|--------------|--------|---------------------|---------------------|
| 19 | `AgentEnvironmentTest.test_agent_process_has_no_vibe_paths` | Startumgebung mit allen sieben Fake-Produktivpfaden | Ein Paketlauf ohne Sandbox | Agentenprozess enthält keinen der sieben Schlüssel | AK6: Agenten erben keine Produktivpfade |
| 20 | `AgentEnvironmentTest.test_agent_process_keeps_its_run_control_variables` | wie #19 | wie #19 | `VIBE_LOGNAME` bleibt gesetzt | AK6: Bereinigung entfernt Pfade, nicht die Laufsteuerung |
| 21 | `QuestionHintTest.test_prompt_contains_runtime_for_ask_and_wait` | wie #19 | wie #19 | Prompt enthält `vibe ask --runtime`, den aufgelösten Laufzeitordner und nach `vibe ask --wait` ein `--runtime` | AK7: Der Agent kann Rückfragen ohne Kenntnis des Produktivpfads stellen und fortsetzen |
| 22 | `SandboxWiringTest.test_agent_runs_in_the_sandbox_with_config_project_and_worktree` | `SANDBOX=on`, Arbeitskopie ohne `.vibe` | Ein Paketlauf mit Fake-`bwrap` | Agent läuft über `bwrap`; `--chdir` = Arbeitskopie; Arbeitskopie und Konfigurationsprojekt schreibbar gebunden; `<projekt>/.vibe` schreibgeschützt gebunden | AK8: Sandbox gilt für den Agenten, auch wenn die Kopie keine `.vibe` enthält; Konfiguration kommt aus dem Projekt |
| 23 | `SandboxWiringTest.test_package_and_final_verification_run_in_the_sandbox` | `SANDBOX=on`, `VERIFY_PACKAGE`/`VERIFY_FULL` schreiben Marker | Ein Paketlauf | Beide Marker entstehen; beide Prüfungen erscheinen als `bwrap`-Aufruf; das jeweilige `env` enthält keinen der sieben Produktivschlüssel | AK8: Paket- und Abschlussprüfung laufen in der Sandbox und mit bereinigter Umgebung |
| 24 | `SandboxWiringTest.test_verification_without_sandbox_is_unwrapped_but_cleaned` | `SANDBOX=off` | Ein Paketlauf | Beide Marker entstehen; kein `bwrap`-Aufruf; `env` enthält keinen Produktivschlüssel | AK8: Auch ohne Sandbox laufen Prüfungen ohne Produktivpfade (fail-closed bleibt bei `on` unberührt) |

Testumfang des Moduls: 7 Tests — die Fälle #19–#24 plus
`SandboxWiringTest.test_android_final_verification_runs_in_the_sandbox_with_clean_environment`
aus Review Runde 1 (§5.8.1).

### 4.5 Angepasste Bestandstests (AK4)

Die Anpassungen sind reine Isolationsmaßnahmen; kein Assertion wurde
abgeschwächt oder entfernt.

| Datei | Anpassung | Zweck |
|-------|-----------|-------|
| `test_ap04_setup_harness.py` | `setup.main(..., environ={"HOME":…,"PATH":…})` sowie `--install <ziel>/_toolchain`, `--logs <ziel>/_logs` | Kein Erben echter Pfade; Installation ausschließlich im Temp-Ziel |
| `test_setup_vibe.py` | `CliFlowTest.run_main` ergänzt `--install self.vibe/_toolchain`, `--logs self.vibe/_logs` und `environ`; direkter `main`-Aufruf im Dry-Run-Test ebenso; `WrapperTest` entfernt alle sieben `VIBE_*`-Schlüssel aus der Wrapper-Umgebung | Der Wrapper startet den echten Setup; eine geerbte Produktivumgebung würde die echte Installation aktualisieren |
| `test_install_lifecycle.py` | `run_main` ergänzt `--install self.toolchain`, `--logs self.vibe/_logs` und `environ`; fehlender `import os` ergänzt | Installation/Laufzeit bleiben im Temp-Bereich; die Rotphase ist der erwartete `TypeError` |

Hinweis: Im Modul `test_install_lifecycle.py` existiert zusätzlich eine
**vorbestehende** Baustelle: Der Helfer `InstallLifecycleBase.install()` ruft
`install_program_files(kit, self.vibe)` auf, während die Produktions-API den
Toolchain-Ordner erwartet (so ruft auch `main` sie mit dem `--install`-Ziel
auf). Deshalb sind dort bereits am HEAD zahlreiche Tests rot (Abschnitt 6).
Diese Baustelle ist nicht B17 und wurde bewusst nicht umgebaut.

## 5. Rotphase (vor der Implementierung)

Alle Läufe mit dem `env -u`-Präfix aus Abschnitt 3, Arbeitsverzeichnis
`/home/vibe/vibe-logs/worktrees/vibe-B17-m3QD8S`.

### 5.1 AK1/AK2/AK3/AK5 — `test_b17_isolation.py`

```bash
env -u VIBE ... python3 -m unittest tests.unit.test_b17_isolation -v
```

Ergebnis: `Ran 10 tests`, `FAILED (failures=1, errors=9)`.

- 9× `TypeError: main() got an unexpected keyword argument 'environ'`
  (alle `run_main`-Fälle) — die neue Schnittstelle fehlt; der Abbruch erfolgt
  vor jedem Schreibzugriff.
- 1× `AssertionError: '--source' not found in '#!/usr/bin/env bash …'` in
  `test_install_wrapper_names_its_own_source` — der Wrapper nennt seine Quelle
  noch nicht.

Damit sind AK1/AK2/AK3/AK5 rot aus genau dem fehlenden Verhalten; die
Snapshot-Prüfungen kommen in der Rotphase noch nicht zum Tragen, weil `main`
vorher abbricht.

### 5.2 AK7 — `test_b17_questions_runtime.py`

```bash
env -u VIBE ... python3 -m unittest tests.unit.test_b17_questions_runtime -v
```

Ergebnis: `Ran 4 tests`, `FAILED (errors=4)`.

```
SystemExit: Unbekannte Option: --runtime
  File ".../bin/vibe", line 5570, in cmd_ask
```

Alle vier Fälle scheitern an der fehlenden Option; `cmd_ask` und `cmd_answer`
kennen `--runtime` noch nicht.

### 5.3 AK8/AK9 — `test_b17_sandbox_argv.py`

```bash
env -u VIBE ... python3 -m unittest tests.unit.test_b17_sandbox_argv -v
```

Ergebnis: `Ran 4 tests`, `FAILED (failures=1, errors=2)`; ein Test grün.

- 2× `TypeError: bwrap_argv() got an unexpected keyword argument 'extra_write_dirs'`
- 1× `AssertionError: ('--ro-bind-try', …/autonomous.json, …) not found`
- `test_without_new_arguments_the_previous_behaviour_stays` ist grün: AK9 ist
  heute bereits erfüllt und bleibt als Regressionsschutz bestehen.

### 5.4 AK6/AK7/AK8 — `test_b17_runner_isolation.py`

```bash
env -u VIBE ... python3 -m unittest tests.unit.test_b17_runner_isolation -v
```

Ergebnis: `Ran 6 tests`, `FAILED (failures=5)`; ein Test grün.

- `test_agent_process_has_no_vibe_paths`:
  `Der Agentenprozess erbt Produktivpfade: VIBE, VIBE_PROFILE, VIBE_INSTALL,
  VIBE_STATE, VIBE_RUNTIME, VIBE_CONFIG_FILE, VIBE_AGENTS_DIR`
- `test_prompt_contains_runtime_for_ask_and_wait`:
  `'vibe ask --runtime' not found in 'Arbeitspaket F1. …'`
- `test_agent_runs_in_the_sandbox_with_config_project_and_worktree`:
  `Der Agent lief nicht über bubblewrap`
- `test_package_and_final_verification_run_in_the_sandbox`:
  `Paketprüfung lief außerhalb der Sandbox`
- `test_verification_without_sandbox_is_unwrapped_but_cleaned`:
  `Die Prüfung erbte Produktivpfade: VIBE, … VIBE_AGENTS_DIR`
- grün: `test_agent_process_keeps_its_run_control_variables` (Regressionsschutz).

### 5.5 AK4 — angepasste Setup-Module

```bash
env -u VIBE ... python3 -m unittest tests.unit.test_ap04_setup_harness -v
env -u VIBE ... python3 -m unittest tests.unit.test_setup_vibe -v
env -u VIBE ... python3 -m unittest tests.unit.test_install_lifecycle -v
```

| Modul | Ergebnis | B17-Rotursache |
|-------|----------|----------------|
| `test_ap04_setup_harness` | 6 Tests, 3 Errors | 3× `TypeError: … 'environ'` |
| `test_setup_vibe` | 49 Tests, 6 Failures, 15 Errors | 11× `TypeError: … 'environ'`; 10 vorbestehende Reds (Abschnitt 6) |
| `test_install_lifecycle` | 43 Tests, 4 Failures, 34 Errors | 6× `TypeError: … 'environ'`; 32 vorbestehende Reds (Abschnitt 6) |

Beispielauszug:

```
TypeError: main() got an unexpected keyword argument 'environ'
  File ".../tests/unit/test_ap04_setup_harness.py", line 73, in run_setup
```

Die Rotphase tritt damit vor dem ersten Schreibzugriff ein. Die Module wurden
im HEAD-Zustand nicht erneut ausgeführt (siehe 3.1).

### 5.6 Rotphase auf Basis 8b07828 (origin/dev ohne B16)

Nach dem Basiswechsel wurde die Rotphase am 19.11.2026 vollständig auf der
tatsächlichen Basis wiederholt. Die Arbeitskopie steht auf `f11f070` (nur
Testdateien und dieser Bericht); die Produktionsdateien sind die Fassungen von
`8b07828` (origin/dev mit AP19- und F32-Squash, ohne B16). Abschnitt 5 bleibt
der ursprüngliche Lauf gegen `d3bed1a`; für die 24 neuen Fälle sind die
Ergebnisse und Ursachen identisch.

Arbeitsverzeichnis war `/home/vibe/vibe-logs/worktrees/vibe-B17-m3QD8S`,
ausgeführt mit Python 3.14.3. Jeder Lauf verwendete exakt dieses Präfix:

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest <modul> -v
```

| Modul | Ergebnis | Rotursachen | Beabsichtigtes B17-Verhalten? |
|-------|----------|-------------|-------------------------------|
| `tests.unit.test_b17_isolation` | 10 Tests: 1 Failure, 9 Errors | 9× `TypeError: main() got an unexpected keyword argument 'environ'` (alle `run_main`-Fälle); 1× `AssertionError: '--source' not found` in `install-vibe.sh` | ja: AK1/AK2/AK3 fehlen; AK5 bricht vor dem Schreibzugriff ab |
| `tests.unit.test_b17_questions_runtime` | 4 Tests: 4 Errors | 4× `SystemExit: Unbekannte Option: --runtime` (3× `cmd_ask` Zeile 5568, 1× `cmd_answer` Zeile 5620) | ja: AK7, `--runtime` fehlt |
| `tests.unit.test_b17_sandbox_argv` | 4 Tests: 1 Failure, 2 Errors, 1 grün | 2× `TypeError: bwrap_argv() got an unexpected keyword argument 'extra_write_dirs'`; 1× `('--ro-bind-try', …/autonomous.json, …) not found` | ja: AK8; der grüne Fall ist der AK9-Regressionsschutz |
| `tests.unit.test_b17_runner_isolation` | 6 Tests: 5 Failures, 1 grün | Agent erbt alle sieben Produktivpfade; `'vibe ask --runtime' not found` im Prompt; „Der Agent lief nicht über bubblewrap“; „Paketprüfung lief außerhalb der Sandbox“; Prüfung erbt die sieben Produktivpfade | ja: AK6/AK7/AK8; grün ist der Regressionsschutz für die Laufsteuerung (`VIBE_LOGNAME`) |
| `tests.unit.test_ap04_setup_harness` | 6 Tests: 3 Errors, 3 grün | 3× `TypeError: … 'environ'` (`test_dry_run_explains_pi_and_its_install_command`, `test_first_install_stores_the_chosen_harness`, `test_update_without_a_new_choice_keeps_the_stored_harness`) | ja: AK4; die drei grünen Fälle rufen `main` nicht auf |
| `tests.unit.test_setup_vibe` | 49 Tests: 6 Failures, 15 Errors | 11× `TypeError: … 'environ'` (alle in `CliFlowTest`); 10 vorbestehende Reds (siehe unten) | ja für die 11 TypeErrors (AK4) |
| `tests.unit.test_install_lifecycle` | 43 Tests: 4 Failures, 34 Errors | 6× `TypeError: … 'environ'` (`AbortTest`, 2× `PreviewTest`, 3× `UninstallTest`); 32 vorbestehende Reds (siehe unten) | ja für die 6 TypeErrors (AK4) |

Damit sind 22 der 24 neuen Abnahmefälle rot; die zwei grünen Fälle sind die
ausdrücklich als Regressionsschutz formulierten Fälle 18 (AK9) und 20 (AK6).
Kein Rotfall stammt aus einem Import-, Umgebungs- oder Fixture-Fehler:
`test_b17_runner_isolation` hat die Vor-B16-Fassung von `bin/vibe-run.sh`
erfolgreich durchlaufen und dabei genau die erwarteten fünf Fehlschläge
erzeugt.

**Anpassungen an der Testinfrastruktur: keine.** Die Basisdrift hat weder die
Runner-Fixtures noch das Laden der Module gebrochen; die bestehenden
Testdateien aus `f11f070` waren unverändert ausführbar. Es wurden keine
Assertions abgeschwächt und keine Fälle entfernt.

**Vorbestehende, nicht B17-bedingte Reds.** Beide Setup-Module enthalten
Fehlschläge in Klassen, die der B17-Commit nicht berührt (`install_program_files`,
`install_launcher`, `register_projects` werden dort direkt aufgerufen):

- `test_setup_vibe`: 6 Failures in `InstallFilesTest`/`LauncherTest`
  (`_toolchain`-Pfaderwartung gegenüber der Produktionsablage direkt unter dem
  übergebenen Wurzelordner), 3 Errors `TypeError: register_projects() missing
  1 required positional argument: 'install'`, 1 Error `FileNotFoundError`
  (`test_installed_launcher_starts_with_all_options`).
- `test_install_lifecycle`: 28 Errors `FileNotFoundError` aus dem Helfer
  `install()` (`install_program_files(kit, self.vibe)` gegenüber der
  `self.toolchain`-Erwartung) und 4 Assertion-Failures in
  `FreshInstallTest`, `PreviewTest` und `UninstallTest`.

Diese Zahlen weichen von den in Abschnitt 6 genannten HEAD-Kopien ab
(9 Failures/4 Errors bzw. 8 Failures/28 Errors). Die Abweichung betrifft
ausschließlich die genannten, vom B17-Commit unveränderten Klassen; sie ist
nicht durch die B17-Teständerungen verursacht und wurde nicht weiter
aufgeklärt. Die unveränderten HEAD-Fassungen der drei Setup-Module wurden
gemäß 3.1 auch diesmal nicht ausgeführt.

**Anker (gleiches `env -u`-Präfix):**

| Modul | Ergebnis |
|-------|----------|
| `tests.unit.test_questions` | `Ran 35 tests`, `OK` |
| `tests.unit.test_sandbox` | `Ran 36 tests`, `FAILED (failures=3)` — dieselben drei Vorlagenfälle `web`, `docker`, `openwrt` wie in der Baseline |

Die Stichprobe der Zeitstempel zeigt keine Schreibzugriffe außerhalb der
Temp-Bereiche: `~/.config/vibe/config.json` (07:43) und
`~/vibe-toolchain` (neueste Datei 10:54) blieben während der Läufe um
11:23–11:24 unverändert. `git status` blieb leer; es wurde kein Commit
erstellt und keine Produktionsdatei geändert.

### 5.7 Fixture-Anpassungen an den Verify-Vertrag (VIBE_VERIFY_RUNTIME)

Nach dem Einsetzen der Implementierung gilt: Agenten- und Verify-Umgebung
enthalten keinen Produktivpfad `VIBE_RUNTIME` mehr; Prüfaufrufe erhalten für
ihre Dauer ausschließlich `VIBE_VERIFY_RUNTIME`. Zwei Fixture-Stellen lasen
noch `$VIBE_RUNTIME` und wurden minimal angepasst.

| Datei:Zeile | Alte Referenz | Neue Referenz | Begründung |
|-------------|---------------|---------------|------------|
| `tests/unit/test_b9_self_repair.py:72` | `"$VIBE_RUNTIME/final-ran"` | `"$VIBE_VERIFY_RUNTIME/final-ran"` | Die Abschlussprüfung läuft mit bereinigter Umgebung; nur `VIBE_VERIFY_RUNTIME` steht dort bereit. Der Marker bleibt am selben Laufzeitort, keine Assertion wurde verändert. |
| `tests/unit/runner_support.py:410` | `os.environ["VIBE_RUNTIME"]` | `os.environ["FAKE_RUNTIME"]` | Der nachgebildete Agent erhält bewusst keinen Produktivpfad. `FAKE_RUNTIME` ist eine reine Fixture-Variable im Prüfkontext und überlebt die Bereinigung, die nur `VIBE*` entfernt. |
| `tests/unit/test_pause_after_package.py:355` | — | `"FAKE_RUNTIME": str(self.root / "_logs")` | Setzt die Fixture-Variable für den Pause-Marker. Der Pfad ist derselbe Laufzeitordner wie zuvor, aber nicht als Produktivvariable. |

Attribution Auftrag 2: Vor der Anpassung lief
`tests.unit.test_pause_after_package` mit `Ran 16 tests`,
`FAILED (failures=3)`. Alle drei Fehlschläge zeigten im nachgebildeten Agenten
`KeyError: 'VIBE_RUNTIME'` (`runner_support.py`, Pause-Marker); die Folgefehler
im Wiederholungsversuch (`git commit` schlägt fehl) sind Nachwirkungen desselben
Abbruchs. Die übrigen 13 Tests des Moduls waren grün. Auf `8b07828` las der
gleiche Fixture-Code `VIBE_RUNTIME`, und die damalige `bin/vibe-run.sh` gab die
Variable unverändert an den Agenten weiter; erst die B17-Bereinigung entfernt
sie. Es handelt sich damit um eine B17-Folge, nicht um ein vorbestehendes
Baseline-Muster (in Abschnitt 6 nicht gelistet). Nach der Anpassung:
`Ran 16 tests`, `OK`.

Ausgeführte Läufe (jeweils mit dem `env -u`-Präfix aus 5.6 im
Arbeitsverzeichnis der Arbeitskopie):

| Modul | Ergebnis |
|-------|----------|
| `tests.unit.test_b9_self_repair` | `Ran 18 tests`, `OK` |
| `tests.unit.test_pause_after_package` (vorher) | `Ran 16 tests`, `FAILED (failures=3)` — `KeyError: 'VIBE_RUNTIME'` |
| `tests.unit.test_pause_after_package` (nachher) | `Ran 16 tests`, `OK` |
| `tests.unit.test_b17_isolation` | `Ran 10 tests`, `OK` |
| `tests.unit.test_b17_questions_runtime` | `Ran 4 tests`, `OK` |
| `tests.unit.test_b17_sandbox_argv` | `Ran 4 tests`, `OK` |
| `tests.unit.test_b17_runner_isolation` | `Ran 6 tests`, `OK` |
| `tests.unit.test_questions` | `Ran 35 tests`, `OK` |
| `tests.unit.test_runner_package_gates` | `Ran 12 tests`, `OK` (nicht angepasst) |

Hinweis zur Wiederholung: Der erste Lauf von `tests.unit.test_questions`
scheiterte mit 1 Failure (`'vibe ask "' not found`), weil der parallel
arbeitende Coding-Agent `bin/vibe-run.sh` während des Laufs aktualisierte
(`QUESTION_HINT` um 11:59:52). Die Wiederholung nach der Aktualisierung ergab
`Ran 35 tests`, `OK`.

`tests.unit.test_f27_keep_changes` wurde nicht angepasst. Der genannte Fall
`test_final_verification_still_blocks_a_dirty_integration_tree` (Zeile 476) war
im Lauf grün; das Modul zeigte jedoch 5 Errors außerhalb dieses Falls
(`AttributeError: … does not have the attribute 'ensure_test_agent'` in
`bin/vibe`). Diese sind vorbestehend: Weder `8b07828` noch der aktuelle
Arbeitsstand definieren `ensure_test_agent`, auf das `mock.patch.object`
zugreift. Sie wurden nicht verändert.

### 5.8 Grünnachweis AK4, Reviewfälle und Review-Runde 2

Review Runde 1 (`docs/reviews/B17-review-1.md`) verlangte Nachbesserungen zu
vier Befunden. Die drei neuen Testfälle wurden vor den Produktionsfixes
geschrieben und auf `1ecfb1d` rot belegt. Alle Läufe mit dem Präfix aus 5.6 im
Arbeitsverzeichnis der Arbeitskopie.

Die Rotbelege 5.8.1-5.8.3 stammen aus der Rotphase `1ecfb1d`. Die dort
zusätzlich dokumentierten Grünnachweise wurden nach der Umsetzung am Stand
`f589acb` ausgeführt (Arbeitskopie `a1217fa`, das nur diesen Reviewbericht
ergänzt). Review Runde 2 (`docs/reviews/B17-review-2.md`) verlangte zusätzlich
die Erzeugungsmeldung von `cmd_ask` sowie die PREFLIGHT-/BARRIER-Hinweise; die
Ergänzungen und ihr Rotbeleg stehen in 5.8.5.

#### 5.8.1 Review Finding 1 (High) — Android-Abschlussprüfung

| Punkt | Inhalt |
|-------|--------|
| Test | `SandboxWiringTest.test_android_final_verification_runs_in_the_sandbox_with_clean_environment` |
| Vorbedingung | `TYPE=android`, `VERIFY_FULL=""`, `SANDBOX=on`; `<install>/verify/verify.sh` schreibt `env` und einen Marker, passende `schreibfuchs-verify.sha` für `check_hash` |
| Aktion | Ein Paketlauf über den echten `bin/vibe-run.sh` mit Fake-Toolchain, Fake-`bwrap` und leerem `VERIFY_FULL` |
| Erwartetes Ergebnis | Lauf endet mit 0; Marker existiert; `verify.sh` erscheint in einem `bwrap`-Aufruf; die sieben Produktivschlüssel fehlen im Prüfprozess; `VIBE_VERIFY_RUNTIME` ist gesetzt und nennt den Laufzeitordner |

Rotbeleg:

```text
Ran 7 tests
FAILED (failures=3)
FAIL … (check='sandbox')
  AssertionError: unexpectedly None : Die Android-Abschlussprüfung lief außerhalb der Sandbox
FAIL … (check='cleaned-environment')
  AssertionError: Lists differ: [] != ['VIBE', 'VIBE_PROFILE', 'VIBE_INSTALL',
  'VIBE_STATE', 'VIBE_RUNTIME', 'VIBE_CONFIG_FILE', 'VIBE_AGENTS_DIR']
FAIL … (check='verify-runtime')
  AssertionError: False is not true : Die Android-Prüfung erhält kein VIBE_VERIFY_RUNTIME
```

Rotursache: `final_verify` ruft den Android-Zweig mit
`bash "$V/verify.sh" "$P" full` direkt auf und umgeht damit Sandbox,
`VIBE_CLEAN_ENV` und `VIBE_VERIFY_RUNTIME`. Genau das fehlende Verhalten wird
geprüft; die drei Teilprüfungen belegen alle drei Aspekte unabhängig.

Grünnachweis nach Implementierung (Stand `f589acb`):

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest tests.unit.test_b17_runner_isolation -v
```

```text
test_android_final_verification_runs_in_the_sandbox_with_clean_environment
Review 1/High: Auch der Android-Direktzweig läuft isoliert. ... ok
...
----------------------------------------------------------------------
Ran 7 tests in 10.575s

OK
```

Der Android-Fall ist darin enthalten; alle sieben Fälle des Moduls sind grün.

#### 5.8.2 Review Finding 2 (Medium) — Fortsetzungsmeldungen

| Punkt | Inhalt |
|-------|--------|
| Test | `QuestionRuntimeTest.test_timeout_and_autonomous_hints_name_the_given_runtime` (Rotphase `1ecfb1d`: zwei `subTest`-Prüfungen; Review-2-Erweiterung siehe 5.8.5) |
| Vorbedingung | Frage unter dem abweichenden `--runtime`; Umgebungs-Laufzeit zeigt auf einen anderen Ordner |
| Aktion | `cmd_ask --runtime <pfad> --wait <id> --timeout 0.01` (Timeout) und derselbe Aufruf bei aktivem autonomen Modus |
| Erwartetes Ergebnis | Timeout-Meldung nennt `vibe ask --wait <id>` und `--runtime <pfad>`; Autonomie-Meldung nennt `vibe answer`, `--runtime <pfad>`, die ID und `--by agent` |

Rotbeleg:

```text
Ran 5 tests
FAILED (failures=2)
FAIL … (hint='timeout')
  AssertionError: '--runtime /tmp/…/pruef-runtime' not found in
  'Rückfrage … noch offen … Fortsetzen mit: vibe ask --wait <id> --timeout 90 …'
FAIL … (hint='autonomous')
  AssertionError: '--runtime /tmp/…/pruef-runtime' not found in
  '… dokumentiere die Entscheidung mit: vibe answer <id> --option <nummer> … --by agent'
```

Rotursache: `_ask_timeout` und `_ask_autonomous` in `bin/vibe` geben die
Fortsetzungsbefehle ohne `--runtime` aus. `subTest` stellt sicher, dass beide
Meldungen im selben Lauf geprüft und beide Rotursachen sichtbar werden.

Grünnachweis nach Implementierung (Stand `f589acb`, vor den Ergänzungen aus
Review 2):

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest tests.unit.test_b17_questions_runtime -v
```

```text
test_timeout_and_autonomous_hints_name_the_given_runtime
Review 1/Medium: Fortsetzungsbefehle nennen den Laufzeitordner. ... ok
----------------------------------------------------------------------
Ran 5 tests in 0.064s

OK
```

#### 5.8.3 Review Finding 3 (Medium) — Guard bei explizitem `--install`

| Punkt | Inhalt |
|-------|--------|
| Test A3a | `UpdateGuardTest.test_update_with_an_explicit_install_on_the_running_instance_is_refused` |
| Vorbedingung | Fake-Produktivbereich mit vorhandener Installation; `environ.VIBE_INSTALL` zeigt darauf |
| Aktion | `--update --yes --install <laufende Installation>` ohne `--source` |
| Erwartetes Ergebnis | Exit 1; Ausgabe nennt `--source`; Fake-Produktivbereich byte-identisch; keine `backup-*`-Ordner |
| Test A3b | `UpdateGuardTest.test_update_with_an_explicit_install_and_source_is_allowed` |
| Aktion | Dasselbe Ziel mit `--source <gültiges Kit>` |
| Erwartetes Ergebnis | Exit 0; `version.json` zeigt die Kit-Version `9.9.9` und die Kit-Quelle |

Rotbeleg A3a:

```text
Ran 12 tests
FAILED (failures=1)
FAIL: test_update_with_an_explicit_install_on_the_running_instance_is_refused
  AssertionError: 0 != 1 : vibe-Setup
  … Installationsort: /tmp/…/produktion/VibeCode/_toolchain …
```

Rotursache: Der Guard in `scripts/setup-vibe.py` schließt mit `not options.install`
jedes explizite `--install` aus, auch wenn es genau die erkannte laufende
Installation ist. A3b war im Rotlauf bereits grün und bleibt der
Autorisierungs-Gegencheck.

Grünnachweis nach Implementierung (Stand `f589acb`):

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest tests.unit.test_b17_isolation -v
```

```text
test_update_with_an_explicit_install_on_the_running_instance_is_refused
Review 1/Medium: Ein explizites ``--install`` befreit den Guard nicht. ... ok
----------------------------------------------------------------------
Ran 12 tests in 0.095s

OK
```

#### 5.8.4 AK4-Grünnachweis (Review Finding 4)

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest tests.unit.test_ap04_setup_harness -v
env -u VIBE … python3 -m unittest tests.unit.test_setup_vibe -v
env -u VIBE … python3 -m unittest tests.unit.test_install_lifecycle -v
```

| Modul | Ergebnis | B17-bezogen grün | Verbleibende Baseline-Reds |
|-------|----------|------------------|----------------------------|
| `test_ap04_setup_harness` | `Ran 6 tests`, `OK` | alle 6 | keine |
| `test_setup_vibe` | `Ran 49 tests`, `FAILED (failures=6, errors=4)` | alle 11 `CliFlowTest`-Fälle mit `environ=` und Temp-Pfaden | 6 Failures + 4 Errors (siehe unten) |
| `test_install_lifecycle` | `Ran 43 tests`, `FAILED (failures=7, errors=28)` | 3 der 6 früheren `TypeError`-Fälle (`AbortTest`, 2× `PreviewTest`); `run_main` übergibt `environ=` und Temp-Pfade | 28 Errors + 7 Failures (siehe unten) |

Baseline-Reds `test_setup_vibe` (6 Failures, 4 Errors):

- 6 Failures in `InstallFilesTest`/`LauncherTest`: die Tests erwarten die
  Programmablage unter `<ziel>/_toolchain`, die Produktion legt sie direkt
  unter dem übergebenen Wurzelordner ab.
  Typisch: `AssertionError: PosixPath('/tmp/…/Vibe/bin/vibe') !=
  PosixPath('/tmp/…/Vibe/_toolchain/bin/vibe')`.
- 3 Errors: `TypeError: register_projects() missing 1 required positional
  argument: 'install'` (Testaufruf einargumentig, Produktionssignatur
  `register_projects(workspace, install)`).
- 1 Error: `FileNotFoundError: …/Mein Vibe Ordner/_toolchain/bin` in
  `InstallFilesTest.test_installed_launcher_starts_with_all_options` (gleiche
  Pfaderwartung).

Baseline-Reds `test_install_lifecycle` (28 Errors, 7 Failures):

- 28 Errors `FileNotFoundError` aus dem Helfer `install()`
  (`install_program_files(kit, self.vibe)` gegenüber der `self.toolchain`-
  Erwartung), typisch `…/Vibe/_toolchain/bin/vibe`.
- 4 Failures aus demselben Pfadversatz bzw. Launcher-Erwartungen:
  `AssertionError: 'copy' != 'backup'`, `AssertionError: True is not false`.
- 3 Failures in `UninstallTest` (`test_uninstall_preview_does_not_require_yes`,
  `test_uninstall_refuses_while_a_run_is_live`,
  `test_uninstall_requires_yes_without_terminal`): Diese Fälle waren vorher
  durch `TypeError` gar nicht ausführbar. Sie scheitern jetzt an ihrer eigenen
  Vorbedingung `self.assertTrue((self.toolchain / "bin" / "vibe").is_file())`,
  weil der Baseline-Helfer `install()` weiterhin nach `self.vibe` statt
  `self.vibe/_toolchain` schreibt. Das ist derselbe dokumentierte
  `_toolchain`-Pfadversatz, nicht die B17-Isolation; `main` erhält
  `environ=` und Temp-Pfade und bricht nicht mehr mit `TypeError` ab.

Sicherheitsstichprobe: Kein Lauf schrieb Produktivpfade. Die Zeitstempel von
`~/.config/vibe/config.json` (07:43) und `~/vibe-toolchain` (neueste Datei
10:54) blieben während der Läufe um 12:20 unverändert; der Rotfall A3a
veränderte ausschließlich den Fake-Produktivbereich unter `tempfile`.

#### 5.8.5 Review Runde 2 (Medium) — verbleibende Antwort-/Fortsetzungshinweise

Review Runde 2 (`docs/reviews/B17-review-2.md`, Finding 1) beanstandete drei
weiterhin `--runtime`-lose Meldungen: die Erzeugungsmeldung von `cmd_ask`
(`bin/vibe:5600`) sowie den PREFLIGHT- und BARRIER-Hinweis in
`bin/vibe_packages.py`. Beide Lücken sind jetzt mit Ausgabenachweis abgedeckt
und auf dem aktuellen Stand (`a1217fa`, Produktionscode wie `f589acb`) rot
belegt.

| Punkt | Inhalt |
|-------|--------|
| Test A1 | `QuestionRuntimeTest.test_timeout_and_autonomous_hints_name_the_given_runtime`, dritter `subTest` `hint='creation'` |
| Vorbedingung | Umgebungs-Laufzeit zeigt auf einen anderen Ordner als das übergebene `--runtime` |
| Aktion | `cmd_ask --runtime <pfad> --project "" --no-wait "Welche Farbe?" --option Rot` (Zeitlimit 0) |
| Erwartetes Ergebnis | Die Zeile `Antwort im Terminal: vibe answer <id> …` nennt zusätzlich `--runtime <pfad>` |
| Test A2 | `PackageHintRuntimeTest.test_preflight_and_barrier_hints_name_the_given_runtime` (zwei `subTest`s) |
| Vorbedingung | Leeres Projekt ohne Git-Repository, `runtime=<temp>/pruef-runtime`, kein autonomer Modus |
| Aktion | `assist_preflight(..., timeout=0)` und `assist_barrier(..., timeout=0)` direkt, Ausgaben über `redirect_stdout` erfasst |
| Erwartetes Ergebnis | `PREFLIGHT: Rückfrage …` und `BARRIER: Rückfrage …` nennen im Antwortbefehl `--runtime <pfad>`; beide Aufrufe enden als `timeout` |

A2-Entscheidung: Es gibt keinen vorhandenen Test, der die Hinweiszeilen
inhaltlich prüft. `test_b9_self_repair.AssistUnitFixture` ruft
`assist_preflight` zwar direkt auf, prüft aber nur den Frage-Lebenszyklus und
die Aktion; die Schrankenläufe in `test_ap10_gates` prüfen die Entscheidung,
nicht den Meldungstext. Statt fremde B9-/AP10-Testdateien um eine
B17-spezifische Assertion zu erweitern, liegt der Ausgabenachweis im
B17-Modul (`PackageHintRuntimeTest`). Damit sind beide Meldungen echt
abgedeckt und nicht nur im Bericht begründet.

Rotbeleg (nach den Ergänzungen):

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest tests.unit.test_b17_questions_runtime -v
```

```text
FAIL: … (hint='creation')
  AssertionError: '--runtime /tmp/…/pruef-runtime' not found in
  'Der Nutzer sieht sie im Dashboard; Antwort im Terminal: vibe answer <id> ...'
FAIL: … (hint='preflight')
  AssertionError: '--runtime /tmp/…/pruef-runtime' not found in
  'PREFLIGHT: Rückfrage <id> gestellt; Antwort im Dashboard oder mit:
  vibe answer <id> --option <1|2|3> oder --text "Anweisung"'
FAIL: … (hint='barrier')
  AssertionError: '--runtime /tmp/…/pruef-runtime' not found in
  'BARRIER: Rückfrage <id> gestellt; Antwort im Dashboard oder mit:
  vibe answer <id> --option <1|2|3> oder --text "Anweisung"'

----------------------------------------------------------------------
Ran 6 tests in 0.063s

FAILED (failures=3)
```

Rotursache: `cmd_ask` gibt die Erzeugungsmeldung als
`"… vibe answer " + qid + " ..."` aus; `assist_preflight` und
`assist_barrier` setzen den Antwortbefehl analog ohne Laufzeitordner
zusammen. Die vier übrigen, vorher grünen Fälle des Moduls bleiben grün (der
Timeout-/Autonomie-Test scheitert ausschließlich im neuen `creation`-Teil).
Die Zähler der unveränderten Module blieben gleich: `test_b17_runner_isolation`
`Ran 7 tests`, `OK`; `test_b17_isolation` `Ran 12 tests`, `OK`.

Sicherheitsstichprobe: Alle neuen Pfade liegen unter `tempfile`; die Aufrufe
erzeugen Fragen ausschließlich im übergebenen `runtime`-Ordner, es wird kein
Produktivpfad geschrieben oder gelesen.

Grünnachweis nach der Umsetzung (Stand `6eeb9a4`; ausgeführt in der Arbeitskopie
`c59de24`, die gegenüber `6eeb9a4` ausschließlich `docs/reviews/B17-review-3.md`
ergänzt — Produktions- und Teststand sind identisch). Befehl mit dem
`env -u`-Präfix aus 5.6 im Arbeitsverzeichnis der Arbeitskopie:

```bash
env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
    -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
    python3 -m unittest tests.unit.test_b17_questions_runtime -v
```

```text
test_preflight_and_barrier_hints_name_the_given_runtime ... ok
test_autonomous_mode_is_read_from_the_given_runtime ... ok
test_cmd_answer_uses_the_given_runtime ... ok
test_cmd_ask_writes_into_the_given_runtime ... ok
test_timeout_and_autonomous_hints_name_the_given_runtime
Review 1/Medium: Fortsetzungsbefehle nennen den Laufzeitordner. ... ok
test_wait_reads_the_answer_from_the_given_runtime ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.139s

OK
```

Damit sind alle sechs Fälle des Moduls grün, einschließlich der drei
`subTest`-Hinweise (`creation`, `timeout`, `autonomous`) und der beiden
PREFLIGHT-/BARRIER-Prüfungen. Die drei übrigen B17-Module wurden mit demselben
Präfix im selben Arbeitsstand geprüft und sind ebenfalls grün:
`test_b17_isolation` `Ran 12 tests`, `OK`;
`test_b17_sandbox_argv` `Ran 4 tests`, `OK`; `test_b17_runner_isolation`
`Ran 7 tests`, `OK` — zusammen 29 Tests.

## 6. Vorbestehende Baseline (nicht B17)

Zum Zeitpunkt des Branches sind Teile der Setup-Suites bereits rot. Das wurde
durch einen Vergleich mit den unveränderten HEAD-Fassungen belegt (siehe 3.1)
und ist **nicht** durch die B17-Teständerungen verursacht:

| Modul | HEAD-Baseline | Ursache (belegt) |
|-------|---------------|------------------|
| `test_setup_vibe.py` | 9 Failures, 4 Errors | `install_program_files(kit, self.vibe)` vs. erwarteter `_toolchain`-Pfad; Launcher-/Registrierungspfade |
| `test_install_lifecycle.py` | 8 Failures, 28 Errors | derselbe API-Versatz im Helfer `install()`; zusätzlich Plan-/Uninstall-Erwartungen |
| `test_sandbox.py` | 3 Failures (von 36) | `SANDBOX_TOOLS` der Vorlagen `web`, `docker`, `openwrt` |
| `test_questions.py` | 35 Tests grün | — |

Nach der B17-Implementierung bleiben diese vorbestehenden Reds bestehen, sofern
sie nicht in einem eigenen Arbeitspaket repariert werden. Sie dürfen nicht
durch Abschwächen der B17-Tests „grün" gemacht werden. Für die B17-Abnahme
zählen ausschließlich:

- die 24 ursprünglichen Tests plus die 5 Reviewfälle (zusammen 29, siehe §1),
- die `environ`/Pfad-Fälle der drei angepassten Setup-Module,
- die beiden Anker (`test_questions` unverändert grün; `test_sandbox` nicht
  schlechter als die Baseline).

## 7. Offene Punkte und getroffene Annahmen

1. **Guard-Grenze (AK2).** Der Guard soll greifen, wenn `--update` das aus
   `environ`/Konfiguration aufgelöste Installationsziel trifft und kein
   `--source` angegeben ist. Ein ausdrücklich übergebenes `--install` muss
   weiterhin ein Update in Temp-Pfaden erlauben; sonst brechen bestehende
   AP04-/Lifecycle-Tests. Diese Auslegung ist vor der Implementierung zu
   bestätigen.
2. **`--source`-Vorrang (AK3).** `--source` muss auch dann gelten, wenn der
   Aufrufer zusätzlich ein `kit=` injiziert (Testfälle 8/9). Eine leere Quelle
   muss vor jedem Schreibzugriff mit `Unvollständiges Quellverzeichnis`
   abbrechen.
3. **AK8-Konflikt mit Bestandstests.** Eine bereinigte Verify-Umgebung entfernt
   `VIBE_RUNTIME`. Zwei bestehende Tests nutzen diesen Pfad aber in ihren
   Prüfbefehlen:
   - `tests/unit/test_runner_package_gates.py:330`
     (`VERIFY_FULL="git status --porcelain > \"$VIBE_RUNTIME/verify.status\""`)
   - `tests/unit/test_b9_self_repair.py:72`
     (`VERIFY_FULL='echo final > "$VIBE_RUNTIME/final-ran"'`)

   Diese Tests wurden bewusst **nicht** angepasst. Die Implementierung muss
   entscheiden, ob sie (a) die Prüfbefehle auf projektrelative Pfade umstellt
   oder (b) für Prüfungen eine dokumentierte, nicht-produktive Variable
   bereitstellt. Eine stille Rückkehr von `VIBE_RUNTIME` in die Verify-Umgebung
   wäre ein Rückschritt und würde Test 23/24 verletzen.
4. **Sandbox-Schnittstelle.** Die Testfälle legen
   `bwrap_argv(..., extra_write_dirs=..., chdir=...)` fest. Die
   Kommandozeilen-Optionen von `vibe_sandbox.py` bleiben frei.
5. **`--runtime`-Umfang.** Die Tests decken `vibe ask` und `vibe answer` ab.
   `vibe autonomous` wird nur über das Modul (`vibe_autonomous`) geprüft, weil
   der Agent den Zustand über `ask --wait --runtime` liest.
6. **Rückfrageordner.** Test 17 erwartet `--bind` (nicht `--bind-try`) für
   `<runtime>/questions`. Das entspricht dem heutigen Verhalten; der Ordner
   wird von der Sandbox angelegt.

## 8. Abnahmekriterien für die Implementierung

1. Alle 29 B17-Tests (24 ursprüngliche + 5 Reviewfälle) sind grün; die
   Zuordnung steht in §1, die Einzelnachweise in §5.7–§5.8.
2. Die `environ`/Temp-Pfad-Fälle in `test_ap04_setup_harness.py`,
   `test_setup_vibe.CliFlowTest` und den `run_main`-Fällen von
   `test_install_lifecycle.py` sind grün.
3. `tests.unit.test_questions` bleibt mit 35 Tests grün.
4. `tests.unit.test_sandbox` ist nicht schlechter als die Baseline
   (33 grün, 3 vorbestehende Vorlagenfehler).
5. Kein Testlauf schreibt außerhalb von `TemporaryDirectory`; die
   Snapshot-/Backup-Prüfungen in `test_b17_isolation.py` belegen das.
6. Die Rotphase dieses Berichts ist nachvollziehbar; die Tests wurden nicht
   abgeschwächt.

## 9. Nicht geprüft / Grenzen

- Keine echten Modell-, Netz- oder Paketmanager-Aufrufe.
- Kein echter `bubblewrap`-Lauf; geprüft wird die Argumentkomposition und die
  Verdrahtung über eine Attrappe.
- Keine Browser-/UI-Prüfung (B17 ist ein Architektur-/Sicherheitspaket).
- Die vorbestehenden Baseline-Fehler in den Setup-Suiten sind dokumentiert,
  aber nicht repariert (außerhalb des B17-Bereichs).
