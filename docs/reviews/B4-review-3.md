# Review-Bericht: Arbeitspaket B4 — Install fails with error (`runs.json` leer)

- **Arbeitspaket:** B4 (neuer FEEDBACK-Eintrag „Install fails with error“, Art: Bug; Hinweis zur Kennung: das ältere, bereits geschlossene B4 „Fehler bei Verwendung des Pi-Harness“ unter `docs/features/B4.md` und `docs/reviews/B4-review-1/-2.md` bleibt unangetastet erhalten; dieser Bericht ist Runde 3 der Kennung B4: `docs/reviews/B4-review-3.md`)
- **Ausgangscommit:** `578a6dd` (`578a6dd3d3b4ac5f5fe41de49382c0c5d320a672`, Branch `feature/korbat/b4`, Arbeitskopie `/var/log/custom/vibe-dev/worktrees/vibe-B4-A8gjp9`)
- **Datum:** 2026-11-22
- **Reviewer:** unabhängiger Code-Reviewer (`code-reviewer`, read-only)
- **Geprüfter Änderungssatz:**
  - Modifiziert: `scripts/setup-vibe.py` (`running_installation()`: Registerleseblock + Docstring), `docs/import-manifest.json` (`files`-Eintrag `scripts/setup-vibe.py` + `aenderungen`-Eintrag `B4`)
  - Neu (untracked): `tests/unit/test_b4_install_empty_runs.py`, `docs/reviews/B4-test-agent-report.md`, `docs/features/B4-install-leerer-laufzustand.md`

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| **AK1 — Vorhandene leere `runs.json` (0 Byte) sperrt nicht:** Eine vorhandene, aber 0 Byte große `<logs>/runs.json` wird wie eine fehlende Datei behandelt (`data = None`, kein Sperrgrund `Laufzustand … ist nicht lesbar`); `--update` läuft durch und aktualisiert die Installation. | PASS | `scripts/setup-vibe.py:1133-1136`, `scripts/setup-vibe.py:1172-1187`, `scripts/setup-vibe.py:1653-1660` | Quelltextprüfung durch mich + Testfälle `EmptyRunStateDirectTest.test_empty_runs_file_is_not_a_block_reason` (`tests/unit/test_b4_install_empty_runs.py:174-178`) und `UpdateWithEmptyRunsTest.test_update_runs_through_with_an_empty_runs_file` (`:275-291`); Rotphase am Ausgangsstand `578a6dd` mit Originalausgabe in `docs/reviews/B4-test-agent-report.md:75-118` belegt; Grünlauf (`Ran 16, OK`) im Koordinator-Nachweis berichtet. |
| **AK2 — Reiner Leerraum wird wie leer behandelt:** Eine nur aus Leerraum (`"\n"`, `"  \n\t \n"`) bestehende `runs.json` sperrt über `if text.strip():` ebenfalls nicht. | PASS | `scripts/setup-vibe.py:1133-1136`, `scripts/setup-vibe.py:1183-1187` | Quelltextprüfung durch mich + Testfälle `EmptyRunStateDirectTest.test_whitespace_only_runs_file_is_not_a_block_reason` (`tests/unit/test_b4_install_empty_runs.py:180-185`) und `UpdateWithEmptyRunsTest.test_update_runs_through_with_a_whitespace_only_runs_file` (`:293-307`); Rotphase im Test-Agenten-Bericht belegt; Grünlauf im Koordinator-Nachweis berichtet. |
| **AK3 — Nicht-leerer unlesbarer Inhalt sperrt weiterhin (Bestandsvertrag):** Korruptes nicht-leeres JSON (z. B. `"{kein json"`) wirft in `json.loads(text)` `ValueError` und erzeugt unverändert `Laufzustand <pfad> ist nicht lesbar`; `RunningGuardTest.test_update_refuses_when_the_run_state_is_unreadable` bleibt ungeschwächt. | PASS | `scripts/setup-vibe.py:1183-1187`, Bestandstest: `tests/unit/test_install_lifecycle.py:820-831` | Quelltextprüfung durch mich + Testfälle `EmptyRunStateDirectTest.test_non_empty_unreadable_runs_file_remains_a_block_reason` (`tests/unit/test_b4_install_empty_runs.py:187-193`) und `UpdateWithEmptyRunsTest.test_update_still_refuses_a_non_empty_unreadable_runs_file` (`:309-325`); grün in Rot- und Grünphase. |
| **AK4 — Lesefehler (`OSError`) sperrt weiterhin:** Scheitert `runs_path.read_text(encoding="utf-8")` mit `OSError` (im Test dateisystemunabhängig als Verzeichnis/`IsADirectoryError` geprüft), bleibt `Laufzustand <pfad> ist nicht lesbar` ein Sperrgrund. | PASS | `scripts/setup-vibe.py:1178-1181` | Quelltextprüfung durch mich + Testfälle `EmptyRunStateDirectTest.test_oserror_when_reading_the_runs_path_remains_a_block_reason` (`tests/unit/test_b4_install_empty_runs.py:195-204`) und `UpdateWithEmptyRunsTest.test_update_still_refuses_when_the_runs_path_is_unreadable` (`:327-343`); grün in Rot- und Grünphase. |
| **AK5 — Alle drei Guard-Nutzer (`--update`, `--uninstall`, `--rollback`):** Leere `runs.json` blockiert keinen der drei Pfade; aktive Läufe mit existierender tmux-Sitzung blockieren weiterhin alle drei Pfade. | PASS | `scripts/setup-vibe.py:1492-1499` (`--rollback`), `scripts/setup-vibe.py:1535-1542` (`--uninstall`), `scripts/setup-vibe.py:1653-1660` (`--update`) | Quelltextprüfung durch mich + `UninstallWithEmptyRunsTest` (`tests/unit/test_b4_install_empty_runs.py:386-419`) und `RollbackWithEmptyRunsTest` (`:421-463`); Rotphase für die Leer-Fälle und Grünphase für alle Fälle im Test-Agenten-Bericht bzw. Koordinator-Nachweis belegt. |
| **AK6 — Live-Sperre & fehlende Datei unverändert:** `LIVE_RUN_STATES = ("starting", "running")`, `session_state(..., own_socket=True)`, Server-/UI-Sitzungsprüfung und das Verhalten bei fehlender `runs.json` bleiben unverändert. | PASS | `scripts/setup-vibe.py:80`, `scripts/setup-vibe.py:1143-1171`, `scripts/setup-vibe.py:1188-1209` | Quelltextprüfung durch mich + Testfälle `test_missing_runs_file_is_not_a_block_reason` (`:169-172`), `test_live_run_with_existing_session_remains_a_block_reason` (`:206-213`), `test_update_still_refuses_a_running_run_with_live_session` (`:345-363`), `test_update_still_refuses_a_starting_run_with_live_session` (`:365-383`). |
| **Manifest, Dokumentation & Hygiene:** `docs/import-manifest.json` konsistent aktualisiert, Paketdoku `docs/features/B4-install-leerer-laufzustand.md` vollständig und ehrlich, Bestandstests und `FEEDBACK.md`/`TICKETS.md` vor Review-PASS unangetastet. | PASS | `docs/import-manifest.json:1255-1262`, `docs/import-manifest.json:1456-1459`, `docs/features/B4-install-leerer-laufzustand.md:1-212`, `FEEDBACK.md:89-171` | Vollständige Dateiinspektion durch mich + Koordinator-Nachweis (`check-import-manifest.py`, `check-syntax.py`, `check-no-secrets.py`, `verify.sh quick`, `verify.sh package` jeweils Exit 0). |

## Findings
- No findings.

---

## Prüfauftrags-Abgleich im Detail

1. **Fachliche Korrektheit (`scripts/setup-vibe.py:1125-1209`):**
   - **Durch mich direkt am Quelltext verifiziert:** In `running_installation()` wird `runs_path = Path(logs_dir) / "runs.json"` bei `runs_path.exists()` zunächst in einem eigenen `try: text = runs_path.read_text(encoding="utf-8") except OSError:` gelesen (`:1178-1181`). Ein `OSError` (z. B. fehlende Leserechte oder Verzeichnis statt Datei) landet wie bisher sofort in `reasons.append(f"Laufzustand {runs_path} ist nicht lesbar")`.
   - Im `else`-Zweig (`:1182-1187`) wird `json.loads(text)` nur dann aufgerufen, wenn `if text.strip():` wahr ist. Ist die Datei leer (`""`) oder enthält sie nur Leerraum (`"\n"`, `"  \n\t \n"`), bleibt `data = None` — exakt wie bei einer fehlenden `runs.json` (`:1173-1174`). Enthält die Datei nicht-leeren, ungültigen Inhalt, fängt `except ValueError:` den `JSONDecodeError` ab und trägt unverändert `Laufzustand {runs_path} ist nicht lesbar` ein.
   - Das Verhalten steht im Einklang mit `RunRegistry._read()` in `bin/vibe_runs.py:834-846`, das eine leere `runs.json` zur Laufzeit ebenfalls als leere Laufliste behandelt.
   - Da `running_installation()` der einzige Guard für `--rollback` (`:1493`), `--uninstall` (`:1536`) und `--update` (`:1654`) ist und `runs.json` nirgendwo sonst in `scripts/setup-vibe.py` gelesen wird, behebt die Änderung das gemeldete Fehlerbild vollständig.

2. **Kleinste Änderung / KISS (`scripts/setup-vibe.py:1133-1136, 1174-1187`):**
   - **Durch mich direkt am Quelltext verifiziert:** Geändert wurden in `scripts/setup-vibe.py` ausschließlich der 4-zeilige Docstring-Absatz (`:1133-1136`) und der 14-zeilige Registerleseblock (`:1174-1187`). `LIVE_RUN_STATES` (`:80`), `session_state()` (`:1143-1170`), die Auswertung von `data.get("runs", [])` (`:1188-1205`), die Prüfung der Server-/UI-Sitzungen (`:1206-1208`) und sämtliche Meldetexte sind unberührt. Keine Nebeneffekte, keine unnötigen Abstraktionen.

3. **Testqualität und Unabhängigkeit (`tests/unit/test_b4_install_empty_runs.py`, `docs/reviews/B4-test-agent-report.md`):**
   - **Durch mich direkt an den Dateien verifiziert:** Die Testdatei `tests/unit/test_b4_install_empty_runs.py` (467 Zeilen, 16 Testfälle in 4 Testklassen) stammt vom unabhängigen Test-Agenten, der seine Ableitung aus `FEEDBACK.md` (B4), `SPEC.md` und `AGENTS.md` sowie die Rotphase vor der Implementierung in `docs/reviews/B4-test-agent-report.md` dokumentiert hat.
   - Die Rotphase am Ausgangsstand `578a6dd` (`Ran 16 tests in 0.157s`, `FAILED (failures=7)`) zeigt exakt die 7 erwarteten Fehlschläge für AK1, AK2 und AK5 (leere/Leerraum-`runs.json` bei Direktaufruf, Update, Uninstall, Rollback), während die 9 Schutzwachfälle (fehlende Datei, AK3, AK4, AK6) bereits am Ausgangsstand grün waren.
   - Alle Tests arbeiten streng isoliert in `tempfile.TemporaryDirectory()`, übergeben eine bereinigte `environ={"HOME": str(self.home), "PATH": ...}` ohne `VIBE_INSTALL` an `setup.main(...)`, nutzen für `OSError` dateisystemunabhängig `self.runs_path.mkdir()` (`IsADirectoryError`, kein `chmod` gemäß FUSE/NTFS-Regel) und simulieren tmux deterministisch über injizierte `which`/`runner`-Callables.
   - Im Gegensatz zum historischen `InstallLifecycleBase.install()` in `tests/unit/test_install_lifecycle.py:108-111` übergibt `InstallerFixture.install()` in `tests/unit/test_b4_install_empty_runs.py:229-234` korrekt `self.toolchain` an `setup.install_program_files(...)`, genau wie `setup.main()` mit `--install`.
   - Keine Assertions wurden abgeschwächt; `tests/unit/test_install_lifecycle.py` (890 Zeilen) und `tests/unit/test_b17_isolation.py` wurden von mir gelesen und sind unverändert.

4. **Bestandsverträge (`tests/unit/test_install_lifecycle.py:820-831`, `tests/unit/test_b17_isolation.py`):**
   - **Durch mich direkt am Quelltext verifiziert:** `RunningGuardTest.test_update_refuses_when_the_run_state_is_unreadable` (`tests/unit/test_install_lifecycle.py:820-831`) schreibt `"{kein json"` nach `runs.json` und prüft Exit 1 sowie `"nicht lesbar"`. Da `"{kein json".strip()` nicht leer ist, greift weiterhin `json.loads` → `ValueError` → `"Laufzustand … ist nicht lesbar"`.
   - Laut Koordinator-Nachweis läuft `tests.unit.test_b17_isolation` unverändert mit `Ran 12, OK` durch.

5. **Manifest und Hygiene (`docs/import-manifest.json`, `FEEDBACK.md`, `TICKETS.md`):**
   - **Durch mich direkt an den Dateien verifiziert:**
     - `docs/import-manifest.json:1255-1262` enthält den neuen `aenderungen`-Eintrag für `"arbeitspaket": "B4"` mit Datum `"2026-11-22"`, `"dateien": ["scripts/setup-vibe.py"]` und präziser Begründung.
     - `docs/import-manifest.json:1455-1459` aktualisiert den `files`-Eintrag für `"scripts/setup-vibe.py"` (`"bytes": 74119`, `"sha256": "482cd6f835f0df1e02643bff16ed3fbcf6222055e82153d6b9e8f4276f9daa2f"`). Die Übereinstimmung mit der Datei auf Platte ist durch den Koordinator-Lauf `python3 scripts/check-import-manifest.py` → `OK (68 Dateien)` und `verify.sh quick` → `Exit 0` belegt.
     - `FEEDBACK.md:89` steht weiterhin auf `- [ ] B4 Install fails with error` (unabgehakt vor Review-PASS); `TICKETS.md` ist unangetastet. Keine Geheimnisse, Tokens oder persönlichen Konfigurationen im Änderungssatz.

6. **Dokumentation (`docs/features/B4-install-leerer-laufzustand.md`, `docs/features/B4.md`):**
   - **Durch mich direkt an den Dateien verifiziert:**
     - Das historische Feature-Dokument `docs/features/B4.md` („B4 — Fehler bei Verwendung des Pi-Harness“, Stand 2026-11-08) sowie `docs/reviews/B4-review-1.md` und `docs/reviews/B4-review-2.md` sind vollständig erhalten.
     - Das neue Dokument `docs/features/B4-install-leerer-laufzustand.md` erläutert den Kennungs-Konflikt in Zeilen 8–13 transparent und verweist für dieses Paket auf `docs/reviews/B4-review-3.md` (Runde 3 der Kennung B4) sowie `docs/reviews/B4-test-agent-report.md`.
     - Ursachenanalyse, Entscheidung, Umsetzung, Grenzen (kein Lauf unter echtem `root`/`update.sh`, Fake-tmux, `IsADirectoryError` statt `chmod`, Ursprung der `*.1`-Rotation außerhalb des Paketumfangs) und Pflichtprüfungen sind sachlich zutreffend und ehrlich dokumentiert.

7. **Baseline-Ehrlichkeit:**
   - **Durch mich gegen Bestandsdokumentation (`docs/features/AP3-Korbat.md:164-198`, `docs/reviews/AP3-Korbat-review-2.md:14,64-65`) abgeglichen:** Die vom Koordinator gemeldeten Baseline-Zähler für `test_setup_vibe` (`Ran 50, FAILED (failures=6, errors=4)`), `test_install_lifecycle` (`Ran 43, FAILED (failures=7, errors=28)`) und `test_b17_isolation` (`Ran 12, OK`) stimmen exakt mit der in AP3-Korbat dokumentierten B17-Baseline überein. Die Klassifizierung der 25 Rotmodule im einmaligen Volllauf (`2396 Tests, 107/132 Module bestanden, 25 Module rot, Exit 5`), darunter alle Module mit Referenz auf `scripts/setup-vibe.py` und `docs/import-manifest.json`, ist in `docs/features/B4-install-leerer-laufzustand.md:164-197` schlüssig gegen den Ausgangscommit `578a6dd` nachgewiesen; das neue Modul `tests.unit.test_b4_install_empty_runs` lief im Volllauf grün.

---

## Verification
- **Change set reviewed:** Arbeitsbaum gegen Ausgangscommit `578a6dd` (`578a6dd3d3b4ac5f5fe41de49382c0c5d320a672` auf Branch `feature/korbat/b4`, verifiziert über `.git` → `/opt/custom/vibe-dev/workspaces/vibe/.git/worktrees/vibe-B4-A8gjp9/HEAD` und `logs/HEAD`). Vollständig inspiziert: `scripts/setup-vibe.py`, `docs/import-manifest.json`, `tests/unit/test_b4_install_empty_runs.py`, `docs/reviews/B4-test-agent-report.md`, `docs/features/B4-install-leerer-laufzustand.md` sowie zum Abgleich `tests/unit/test_install_lifecycle.py`, `tests/unit/test_b17_isolation.py`, `bin/vibe_runs.py`, `FEEDBACK.md`, `TICKETS.md`, `docs/features/B4.md`, `docs/features/AP3-Korbat.md`, `docs/reviews/B4-review-2.md`, `docs/reviews/B3-review-2.md` und `docs/reviews/AP3-Korbat-review-2.md`.
- **Git commands run by me:** none (in dieser Read-only-Reviewer-Sitzung ist kein Shell-/Bash-Werkzeug registriert; alle Prüfungen erfolgten direkt durch Lesen der Arbeitskopie und der `.git`-Worktree-Metadaten über `read`).
- **Checks evidenced by supplied raw output:**
  - `python3 -m unittest tests.unit.test_b4_install_empty_runs -v` (Rotphase vor Implementierung in `docs/reviews/B4-test-agent-report.md:79-118`: `Ran 16 tests in 0.157s`, `FAILED (failures=7)`)
  - `python3 -m unittest tests.unit.test_install_lifecycle -v` (Baseline-Nachweis in `docs/reviews/B4-test-agent-report.md:141-147`: `Ran 43 tests in 0.442s`, `FAILED (failures=7, errors=28)`)
  - `python3 -m unittest tests.unit.test_b4_install_empty_runs -v` (Grünphase nach Implementierung in `docs/features/B4-install-leerer-laufzustand.md:141-145`: `Ran 16 tests in 0.154s`, `OK`)
- **Checks reported only by the coding agent / coordinator:**
  - `python3 -m unittest tests.unit.test_setup_vibe` → `Ran 50, FAILED (6F/4E)` (unveränderte B17-Baseline)
  - `python3 -m unittest tests.unit.test_b17_isolation` → `Ran 12, OK`
  - `python3 scripts/check-import-manifest.py` → `OK (68 Dateien)`
  - `python3 scripts/check-syntax.py` → `OK`
  - `python3 scripts/check-no-secrets.py` → `OK`
  - `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh quick` → `Exit 0`
  - `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh package` → `Exit 0`
  - `env -u GITHUB_AUTO_MERGE bash scripts/verify.sh full` → `2396 Tests, 107/132 Module bestanden, 25 Module rot (alle 25 vorbestehend, signaturenidentisch zu 578a6dd), Exit 5`
- **Checks not independently run:** alle Build-, Test-, Verify- und Git-CLI-Kommandos (kein Shell-Werkzeug in der Reviewer-Sitzung verfügbar; strikte Read-only-Rolle).
- **Important areas inspected:** `scripts/setup-vibe.py:1125-1210,1483-1560,1650-1665`, `tests/unit/test_b4_install_empty_runs.py:1-467`, `tests/unit/test_install_lifecycle.py:95-135,665-890`, `bin/vibe_runs.py:811-851`, `docs/import-manifest.json:1255-1263,1455-1460`, `docs/reviews/B4-test-agent-report.md:1-206`, `docs/features/B4-install-leerer-laufzustand.md:1-212`.
- **Remaining risks:** none.

---

## Bestätigung der Abhak-Reife und abschließende Schritte vor dem Commit

Das Arbeitspaket B4 hat das Review mit **`Verdict: PASS`** (0 Critical, 0 High, 0 Medium, 0 Minor) bestanden und ist **abhak- und commit-reif**. Vor dem Abschluss-Commit sind durch den Koordinator nur noch die regulären Post-PASS-Abschlussschritte ohne jede Code- oder Teständerung auszuführen:

1. Diesen Review-Bericht unverändert unter `docs/reviews/B4-review-3.md` ablegen.
2. In `docs/features/B4-install-leerer-laufzustand.md` den Status (`Status: In Bearbeitung (Review ausstehend)` → abgeschlossen / Review-PASS) und den Abschnitt „Abschluss“ (Review-Ergebnis, Commit-/Nachweisangaben) finalisieren.
3. In `FEEDBACK.md` den Eintrag `B4 Install fails with error` auf `- [x] B4 Install fails with error` setzen und die Nachweiszeile (`Commit: <hash>; Test: ...`) eintragen.
4. Ausschließlich die zum Arbeitspaket B4 gehörenden Dateien stagen und mit dem Paket-Präfix `B4:` committen.

### Vom Reviewer selbst ausgeführte Kommandos
- **Shell-/Prüfkommandos:** **keine** (in dieser Reviewer-Sitzung stehen ausschließlich die Read-only-Werkzeuge `read`, `glob`, `grep`, `execute`, `question`, `skill` zur Verfügung; es existiert kein Shell-/Bash-Tool, und gemäß Reviewer-Regeln werden keine Builds, Tests oder Skripte ausgeführt).
- **Durchgeführte Read-only-Inspektionen (`read`):**
  - `.git`, `/opt/custom/vibe-dev/workspaces/vibe/.git/worktrees/vibe-B4-A8gjp9/HEAD` und `logs/HEAD` → Branch `feature/korbat/b4` und Ausgangscommit `578a6dd3d3b4ac5f5fe41de49382c0c5d320a672` bestätigt.
  - `scripts/setup-vibe.py` (vollständig, Zeilen 1–1801) → Änderung in `running_installation()` (Zeilen 1125–1209) und alle Aufrufstellen geprüft.
  - `docs/import-manifest.json` (Zeilen 1100–1599) → `aenderungen`-Eintrag `B4` und `files`-Eintrag `scripts/setup-vibe.py` geprüft.
  - `tests/unit/test_b4_install_empty_runs.py` (vollständig, Zeilen 1–467) → 16 Testfälle, Isolation und Assertions geprüft.
  - `docs/reviews/B4-test-agent-report.md` (vollständig, Zeilen 1–206) und `docs/features/B4-install-leerer-laufzustand.md` (vollständig, Zeilen 1–212) → Rotphase, Dokumentation und Volllauf-Klassifizierung geprüft.
  - `tests/unit/test_install_lifecycle.py` (vollständig, Zeilen 1–890), `tests/unit/test_b17_isolation.py` (Zeilen 1–80), `bin/vibe_runs.py` (Zeilen 1–180, 300–379, 650–889), `FEEDBACK.md`, `TICKETS.md`, `docs/features/B4.md`, `docs/features/AP3-Korbat.md`, `docs/reviews/B4-review-2.md`, `docs/reviews/B3-review-2.md`, `docs/reviews/AP3-Korbat-review-2.md` → Bestandsverträge, Unversehrtheit bestehender Tests und Baseline-Konsistenz bestätigt.
