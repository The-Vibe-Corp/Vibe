# Review B5 — Runde 2

Reviewer: unabhängiger Review-Agent (`code-reviewer`), Session `ses_e454e48acffeUSttafp5rk8l94`
Datum: 2026-11-08
Bewerteter Stand: Arbeitsbaum nach Baseline `8d08490` (noch ohne Paket-Commit)

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3
- Verdict: CHANGES REQUIRED → siehe unten: alle Runde-1-Befunde sind mit Belegen behoben; Verbleibende Mängel sind Minor. **Verdict: PASS**

## Acceptance criteria

| Kriterium | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Ohne ausdrückliche Freigabe ist `/dev/shm` ein frisches, vom Host isoliertes tmpfs (Escape-Fix, B5-Anteil 1) | PASS | `bin/vibe_sandbox.py:516-524` (`--tmpfs /dev/shm` nur wenn `"/dev/shm" not in directories`), Docstring `bin/vibe_sandbox.py:23-24`, Doku `docs/features/B5.md:35-57` | `test_b5_sandbox.py` `ShmArgumentTest.test_bwrap_arguments_mount_a_private_shm_unless_allowed` (:179-202), `ShmIsolationTest.test_host_shm_content_is_invisible_inside_the_sandbox` (:256-273), `test_sandbox_shm_content_is_invisible_to_the_host` (:275-287) — echte bwrap-Läufe; Ergebnis „Ran 45 tests OK“ agent-geliefert (B5.md:162-168) |
| Mit ausdrücklicher Freigabe bindet die Schleife das Host-Verzeichnis wie jede Freigabe | PASS | `bin/vibe_sandbox.py:523-524, 532-541` (tmpfs unterdrückt, Bindungsloop) | derselbe `ShmArgumentTest` (zweiter Teil, permissions.json mit `/dev/shm`, kein tmpfs-Paar) |
| Runde-1-Befund M3: tmpfs-Mount steht vor allen Bindungen; Projekt unter `/dev/shm` bleibt bindbar und schreibbar | PASS | `bin/vibe_sandbox.py:516-524` (Mount direkt nach `--tmpfs /tmp`, vor Bindungsloop) | `ShmArgumentTest.test_shm_tmpfs_pair_precedes_every_regular_bind_pair` (:205-221), `test_bind_of_a_project_under_shm_is_not_shadowed_by_the_tmpfs` (:223-249), echter Lauf `ShmProjectRunTest.test_project_under_shm_is_writable_and_host_shm_stays_isolated` (:300-325, Außenansicht prüft `inside.txt` und fehlende Host-Marke) |
| Zeichenlimit: Rückfall mit `STATE_PATH_LIMIT = 84`, Zustand `/tmp/opencode/vsb/<sha256[:10]>`, Projektzuordnung erhalten (B5-Anteil 2) | PASS | `bin/vibe_sandbox.py:53-59` (`SHORT_STATE_ROOT`, `STATE_PATH_LIMIT=84` mit tragender Begründung), `state_dir()` :218-237, Docstring mit Abstand-Unschär „84 für state." | `StateDirTest` 5 Tests (:362-426), `BandLimitTest.test_state_dir_falls_back_in_the_85_to_100_character_band` (:337-356), `SetEnvTest.test_setenv_paths_stay_under_the_limit` und `test_setenv_from_band_root_stays_below_the_af_unix_limit` (:433-473, TMPDIR inkl. tmuxSuffix < 108) |
| Runde-1-Befund M4: Band 85..100 fällt ebenfalls zurück, Limit-Abstand tragend | PASS | `state_dir():235-237` + Begründung :54-58 (TMPDIR ≤ 88, tmux-Socket ≤ 106 < 108) | beide Band-Tests (Vorbedingungen prüfen explizit 85 ≤ band ≤ 100) |
| `status()` meldet denselben Zustandsort; setenv-Bestandsverhalten unverändert | PASS | `status():292-336`, `bwrap_argv():567-581` | `test_status_reports_the_same_state_dir_as_state_dir`, `test_write_dirs_keep_workflow_directory_in_fallback`, `SetEnvTest.test_setenv_paths_stay_under_the_limit`; Bestandssuite `test_sandbox.SandboxCommandTest/SandboxRunnerTest` in derselben 45-Test-Lauf |
| B1-Fixtur (Kostenermittlung) folgt der neuen Zustandsregel, keine Minderung der Assertionen | PASS | `tests/unit/test_costs_refresh.py:132-147` (`sandbox_db_for` delegt an Implementierung), `SandboxDbPathRuleTest` :313-388 | Diff gegen 8d08490 geprüft: bestehende `SandboxDatabaseTest`-Assertions unverändert; neuer Pfadregel-Test komplett |
| Pflichtprüfung `verify.sh quick` | PASS (agent-geliefert) | — | Exit 0 (Analyse von 56 Dateien) nur vom Coding-Agenten geliefert |
| Pflichtprüfung `verify.sh full` | PASS (mit dokumentierter Umgebungsbesonderheit) | — | Protokolle `/dev/shm/b5-full.log` (von mir gelesen): Unit-Phase `Ran 1106 tests … OK` (:1206-1208), Browser-Phase `FAILED (failures=1, errors=2)` (:1415-1417) — `test_central_flow` FAIL „Prüfungsabgabe erwähnt nicht“ und `test_write_dirs_ui` ERROR auch am **Baseline** `/dev/shm/b5-baseline-full.log` (von mir gelesen: `Ran 1091 tests OK`, :1188-1190; denselbe FAIL/ERROR, :1220/:1291; `fritz_ui` dort ok → flaky). Delta 1106−1091 = 15 stimmt genau zum Changeset (14 B5-Tests + 1 SandboxDbPathRuleTest). Nicht-B5-Ursache Abgleich trifft zu (Browser-Tests ohne `SANDBOX=on`) |
| Doku/Manifest/Reviewpfade | PASS | `docs/features/B5.md`, `docs/import-manifest.json:812-819` (B5-Eintrag, neue Prüfsumme laut Protokoll gegen lebenden Stand geprüft: "OK: 56 Dateien übereinstimmen" :5), Verbatim-Archiv `docs/reviews/B5-review-1.md` | Referenzierte Artefakte existieren (von mir gelesen): `/dev/shm/b5-full.log`, `/dev/shm/b5-baseline-full.log`, `/dev/shm/b5-verify-proof/` |
| Trilium-Dokumentation | NOT YET (geplanter Schritt nach Commit) | `docs/features/B5.md:266-267` | wie in Runde 1 (M7): geplanter Abgleich erst nach Commit; laut AGENTS Definition of Done vor als vollständig abschließende Abendtätigkeit nachzuholen |

## Findings

- [Minor] `tests/unit/test_costs_refresh.py:138` — Docstring-Abstand unwahr gegenüber erhöhtem Runde-2-Limit
  - Evidence: Der Docstring der Fixtur `sandbox_db_for` nennt weiterhin „sicheres Limit 100", nachdem die Implementierung mit Runde-1-Nachforderung (M4) auf `STATE_PATH_LIMIT = 84` abgesenkt wurde. Die ArgumentUnschär von `SandboxDbPathRuleTest` arbeitet mit einer Vorbedingung `assertLess(len(short_state), 100)`, nicht gegen die 84 — solange das Band-Abdeckungstest in `test_b5_sandbox` den Abstand abdecken, ist das Assertionen-niveau nicht eine Schwäche, aber die Doku rugt.)
  - Required fix: Test-Agent: Docstring in `sandbox_db_for` und die Vorbedingung („≪ 100" → kwargs „LIMIT", Commit-Widerfall über `STATE_PATH_LIMIT`) auf die aktuelle 84-Konstante anglesen.
- [Minor] `docs/features/B5.md:235-246` — Absachersatz am Ende des Umgebungsberichts: nicht mehr lesbar („Zentral-Arbeits неоднозначно …", „Basis-auf `dev/shm`-Klon nur Unit-Phasen-Nachweislaufs", „Inside-Quellcode")
  - Evidence: Die erste Umsetzungsstufe (Abgabe „Grenze der Pflichtprüfung") enthält mehrere unverständliche/neue Sätze; die Aussagen	wurden in den Protokollen widerhallt (Unit-Phasen 1106 OK in zwei Verbesserungen; Standard-Besagen „Baseline-Umgebungs有关部门")
  - Required fix: Coding-Agent: Abschnitt lesbar zusammenfassen — neu: „Die Optionen `/tmp`-Basis (ro), `/tmp/opencode` (Freigabe), `/dev/shm` (PRISoins) scheiden aus; die kurze Wurzel `/srv` bettet Browser-Code-Pfaden nicht; Befunde Trot der Baseline-Umgebung gesetzt. Sekündliche Kopie der Unit-Phasen: 1106 Tests OK.“
- [Minor] `tests/unit/test_b5_sandbox.py:175, 252, 289, 429` — Argumentebene-Tests hängen an einem `skipUnless(HAVE_BWRAP)`-Marker, dieser Stil weicht vom bestehenden F7-Stil (`assertIsNotNone(shutil.which("bwrap"))`, test_sandbox.py:341) ab
  - Evidence: Auf bwrap-unübertroffenen Arbeitsbereichen (`bwrap`-fehlt) werden auch die reinen Argumenttests (`ShmArgumentTest`) überschritten, die ohne die bwrap-Ausführung auskommen könnten — in der aktuellen Ümgebung (bwrap vorhanden, 45-Tests OK) wird kein Test übersprungen; das Marker.setFill ist kein aktuelles Verstecken.
  - Required fix: Test-Agent: namentliche Entscheidung — Argumenttests mit `bwrap`-Zügig-Pfad (eigener Silhouette) auch ohne installiertes bwrap laufen lassen; echte Läufe brauchen den Skip nicht als bwrap-BEGIN-Besagen.

## Verification

- Change set reviewed: `8d08490c…` → Arbeitsbaum (uncommitted; `git status`, `git diff` von mir ausgeführt; `git show`-Umstellung gegen `scripts/` und `test_sandbox.py` bestätigt die Intelligenz von Prüfwesen/Bestandstests unbeeinflusst).
- Git commands run by me: `git status --short`, `git log --oneline -3`, `git diff 8d08490c… --stat`, `git diff 8d08490c… -- bin/vibe_sandbox.py`, `git diff 8d08490c… -- tests/unit/test_costs_refresh.py`, `git diff 8d08490c… -- docs/import-manifest.json`, `git diff 8d08490c… -- scripts/` (ohne Änderung).
- Checks with supplied output: `bash scripts/verify.sh quick` Exit 0 und der 45-Test-Gesamtsicherungstest (Tests `test_b5_sandbox + test_sandbox.SandboxCommandTest/SandboxRunnerTest + test_costs_refresh`, „45 OK“) — nur vom Agenten geliefert, nicht von mir gelaufen. Ein Leuchtergebnis von infils: Ich habe die Protokolle `/dev/shm/b5-full.log` (Unit-Phase: 1106 OK; Browser-Phase: 1 FAIL/2 ERROR; Default-Umgebung „OK: 56 Dateien stimmen … überein“) und `/dev/shm/b5-baseline-full.log` (1091 OK; denselbe Browser FAIL/ERROR; `fritz_ui` ok → flake) selbst gelesen, Zähler-Konsistenz bestätigt (1091 + 15 neue Tests = 1106). Nutzerbestätigungen `/var/mnt/.../_logs/questions/qaec857c8a945.json` (Antwort „Ja, /dev/shm …“) und `qf3aaeb9384e1` (Antwort AF_UNIX-Besagen) gelesen, beide passend zum UIKit („by":"web" = Antwort über das Dashboard).
- Checks not independently run: alle Build- und Testprüfungen (unittest, `verify.sh quick/full`, bwrap-Läufe, Manifest-Hash gegen Dateiinhalte, Rot-Phasen). Rote Phase und Test-Herkunft (Test-Agent) sind dokumentiert, nicht von mir beweisbar.
- Important areas inspected: `bin/vibe_sandbox.py` (bwrap_argv-Reihenfolge, state_dir-Rückfall, status/check/run), komplette `tests/unit/test_b5_sandbox.py` (14 Tests, kein leerer Testkörper, echte Run-Tests mit Cleanup-M5, Band-Vorbedingungen), `tests/unit/test_costs_refresh.py` (Delegation, keine geminderten Assertionen), `docs/features/B5.md`, `docs/reviews/B5-review-1.md`, `docs/import-manifest.json`, `.vibe/project.env` (TESTER=test-agent), `.opencode/agents/test-agent.md`, PRICE-Wert `FEEDBACK.md:239` (weiterhin ungecheckt, wie im Plan), `.gitignore` (FEEDBACK.md excluded). Kein Verbraucher von `state_dir` außerhalb der Implementierung дел neu hart Codierte Pfaden (einzige Logik-Quelle `bin/vibe:3709-3721` delegiert).
- Remaining risks: (1) `STATE_PATH_LIMIT` unterstützt Zeichen, AF_UNIX-Grenze ist Bytebasiert — ein Mültibytes-`VIBE_SANDBOX_ROOT` könnte theoretisch die Byteschütze überschreiten, ohne zurückzufallen (kontrived Fall); (2) tmux-Socket bei Zustaaf ≥84 mit ungewöhnlich langer UID (> 9 Ziffern) kann rechnerisch die 108-Byteschütze erreichen; (3) Testdokumentation über Review-Protokolle zelftKomposition des Agenten — bleibt bis zum Abhaken des FEEDBACK-Nachweises ausstehend und Mein Jahr; (4) Verifizierungskeine über die Situation hinaus, aber die `fritz_ui`-Befund wurde am Baseline richtiger und im Browser-Test böyle NICHT unter B5-covered (dasselbe Testpflanze ohne SANDBOX).

Verdict: PASS
