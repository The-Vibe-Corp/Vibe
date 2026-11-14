# Review B4 — Runde 1

Datum: 2026-11-08
Reviewer: unabhängiger Code-Reviewer (`code-reviewer`, projektfest konfiguriert, Model `GLM-5.3-Flash Free`; keine Delegation)
Paket-Commit: `c139f84` („B4: Pi-Agentenordner in der Sandbox umleiten …“), Ausgangscommit `11817c3`
Geprüft: `git diff 11817c3..c139f84` vollständig (bin/vibe_sandbox.py +29/−2, docs/compatibility.md +20/−3, docs/features/B4.md neu 180 Zeilen, docs/import-manifest.json +10/−2, tests/unit/test_b4_pi_agent_dir.py neu 399 Zeilen); Arbeitskopie sauber, HEAD = `c139f84`; FEEDBACK.md-Eintrag B4 unverändert (git-excluded); keine Änderungen an Tests des Bestands, Prüfskripten oder `_toolchain` (numstat geprüft).

## Ergebnis

Verdict: **CHANGES REQUIRED** (PASS wegen 1 Medium-Befund nicht möglich)

- Critical: 0
- High: 0
- Medium: 1
- Minor: 2

## Akzeptanzkriterien

| Kriterium | Status | Implementierung (Datei:Zeile) | Test / Nachweis |
|---|---|---|---|
| AK1: `--setenv PI_CODING_AGENT_DIR <Zustandsort>/pi/agent` genau einmal, Ordner angelegt, Zustandsort in `write_dirs`, vorfindliche Umgebungsbelegung wird überschrieben | PASS | `bin/vibe_sandbox.py:580–584` (inkl. bewusstem Override, kommentiert 576–579), Ordneranlage `_ensure_dir` :581–583 | `tests/unit/test_b4_pi_agent_dir.py:165` (`SetEnvTest.test_bwrap_argv_sets_pi_agent_dir_exactly_once_under_state`) und `:191` (`…_wins_over_a_preexisting_environment_variable`); beide als „ok“ im Prüflog b4-verify-full.log:103–109 bestätigt |
| AK2: vorhandene `~/.pi/agent/auth.json` nur lesend an `<Zustandsort>/pi/agent/auth.json` gebunden, keine Schreibbindung, Quelldatei unverändert | PASS | `bin/vibe_sandbox.py:585–593` (`--ro-bind` hinter Dateiexistenzprüfung) | `test_b4_pi_agent_dir.py:218` (`AuthBindTest.test_auth_json_is_read_only_bound_into_the_pi_agent_dir`), Befund „ok“ (Log :103) |
| AK3: fehlende `auth.json` erzeugt keine Bindung, kein Abbruch, Setenv bleibt | PASS | `bin/vibe_sandbox.py:591–592` (`isfile`-Guard, kein else-Pfad) | `test_b4_pi_agent_dir.py:263` (`MissingAuthTest.test_empty_home_binds_no_auth_file_but_keeps_the_setenv`), Befund „ok“ (Log :105) |
| AK4: SANDBOX off — Lauf ohne bwrap und ohne `PI_CODING_AGENT_DIR` | PASS | `bin/vibe_sandbox.py:616–621` (`run()` executes ohne Sandbox, `bwrap_argv` wird nicht betreten) | `test_b4_pi_agent_dir.py:291` (`DisabledSandboxTest.test_print_command_off_shows_plain_command_without_pi_agent_dir`), Befund „ok“ (Log :104) |
| AK5: echter bwrap-Lauf — Schreiben nach `$PI_CODING_AGENT_DIR/trust.json.lock` gelingt, Datei auf dem Host sichtbar, fremdes `HOME` verweigert, Aufräumbeweis | PASS | `bin/vibe_sandbox.py:536–537` (Zustandsort-Bind vor /tmp-Remount), :580–584 | `test_b4_pi_agent_dir.py:322` (`PiAgentDirRunTest.test_pi_agent_dir_writable_state_visible_and_home_denied`), Befund „ok“ (Log :106) |

Nachweisquelle eigenständig gelesen: `/tmp/opencode/vibe-sandbox/vibe-B4-a98BaT-174aaca080/tmp/b4-verify-full.log` (Zeilen 5–7: Manifest 56 Dateien OK, Syntax 109 Python/8 Bash/4 JSON, keine Geheimnisse; :103–109: alle 6 B4-Tests „ok“; :1800–1804: `Ran 1149 tests`, `FAILED (failures=36, errors=2)`, Prüf-Exit 5) sowie `b4-baseline-verify.log:1830–1835` (`Ran 1143 tests`, `FAILED (failures=37, errors=4)`, Exit 5) und beide FAIL-Listen (`b4-full-fails.txt` 38 Einträge, `b4-baseline-fails.txt` 41 Einträge). Eigenständig verglichen: die B4-FAIL-Menge ist echte Teilmenge der Baseline; die drei Baseline-Differenzen sind die zwei `FeedbackBlockStructureTest`-ERROR (an die git-excluded FEEDBACK.md gebunden, im Baseline-Klon abwesend) und `test_real_sandbox_allows_questions_but_not_the_web_token` (flake, nur im Baseline). Alle anderen Sandbox-FAILs (z. B. `test_real_sandbox_allows_write_dirs_and_denies_unlisted_paths` mit `HOME_OPEN`) treten am Baseline identisch auf — keine B4-Regression. Testsstand 1143 → 1149 (+6 = genau die neuen B4-Tests).

## Befunde

### Medium 1 — `bin/vibe_harness.py:325–327`: Der dem B4-Defekt zugrundeliegende falsche Kommentar bleibt stehen

- Evidence: Der Codekommentar lautet: „Ohne Sitzungsdatei schreibt Pi nichts in ~/.pi/agent und funktioniert damit auch in der Schreib-Sandbox, deren Wurzeldateisystem nur lesend eingebunden ist.“ Das ist exakt die Fehlannahme, die B4 nachweislich widerlegt: Pi legt selbst mit `--no-session` `trust.json.lock` an (Ticket-Log, FEEDBACK.md:313–329; Befund AK5). Das Paket korrigiert diese Aussage an zwei Stellen (`docs/compatibility.md:45–56` und Modul-Doku `bin/vibe_sandbox.py:13–23`), lässt sie aber im Harness selbst stehen. Wirkungsmangel: Lesende von `run_argv()` leiten daraus erneut das alte (falsche) Verhalten ab; Doku und Code widersprechen sich. Kein Verhaltensfehler, aber eine unsachliche Bestandsaussage am Direktzustand des Tickets.
- Required fix: Nur den Kommentar in `bin/vibe_harness.py:322–334` korrigieren (gilt: `--no-session` macht den Lauf nicht Sandbox-tauglich, die Sandbox stellt über `PI_CODING_AGENT_DIR` den Agentenordner bereit, funktionale Befehlszeile bleibt unverändert); danach die Harness-Tests und `bash scripts/verify.sh quick` wiederholen, keine weiteren Implementierungsänderungen, erneuem Review vorlegen (diese Änderung ist in B4 in scope: derselbe Defekt).

### Minor 1 — `docs/features/B4.md:171–175`: Trilium-Referenz als vorhanden formuliert, existiert aber nicht

- Evidence: Die Sektion „Review und Dokumentation“ schreibt: „Trilium: Eintrag unter ‚Features‘ (vibe-Projekt); die Referenz steht im FEEDBACK-Eintrag B4.“ Eigenständige Trilium-Prüfung: `resolve_note_id("vibe")` → `sDzCzfWQVOXF`, Kindnotiz-Liste (Features, `IjRpjYJTtqam`, 58 Einträge) enthält keinen B4-Eintrag; Suche mit Titel-Präfix „B4“ und Textsuche „trust.json.lock“ liefern leer. Der FEEDBACK-Eintrag B4 (Zeile 313–329) enthält noch keine Referenz- und Commitzeilen. Das verletzt die Projektregel, dass eine Trilium-Dokumentation nicht herbeigeschrieben werden darf, wenn sie noch nicht existiert (B5-Vorbild: `docs/features/B5.md` kennzeichnete den Eintrag ausdrücklich als Post-Commit-Schritt).
- Required fix: Vor dem Abschluss-Commit den Trilium-Eintrag tatsächlich schreiben und die Referenz (Notiz-ID) in B4.md und FEEDBACK-Eintrag B4 aufnehmen — oder die Formulierung in B4.md auf „nach Review-PASS“ umstellen wie in B5. Die Implementierung selbst ist nicht betroffen.

### Minor 2 — Rotphasen- und echter-Pi-Lauf liegen nur textlich vor (keine Protokolldateien)

- Evidence: Die Ergebnisse „Rotphase: Ran 6 tests, FAILED (failures=2, errors=3)“ und „Pi-Fehlausgabe `No API key found …`“ sind Textausgaben in `docs/features/B4.md:128–137` und der Paketbegründung; unter `/tmp/opencode/vibe-sandbox/vibe-B4-a98BaT-174aaca080/tmp/` existieren nur `b4-verify-full.log`, `b4-baseline-verify.log`, `b4-full-fails.txt`, `b4-baseline-fails.txt` (kein Rotphasen-Log, kein Pi-Lauf-Log). Absicherung: nachvollziehen aus dem Stand 11817c3 — dort gibt es keinen `PI_CODING_AGENT_DIR`-Block, die AK1–AK3-Assertions können daher nicht grün gewesen sein; die AK5-Verneinung (missing state-Pfad) entspricht dem gemeldeten `PI_WRITE_FAILED`. Der Beweis ist trotzdem nicht artefaktisch gesichert.
- Required fix: Nicht für die Abnahme blockierend. Für Folgepakete: Rotphasen- und Integration-Läufe als Protokolldateien (unter `/tmp/opencode/…` wie die verify-Logs) hinterlegen, damit der Reviewer sie nachlesen kann, statt Aussagen zu betreiben.

## Freibleibende Folgerungen

- Der Kompromiss „settings.json/models-store.json nicht binden“ ist nachvollziehbar und transparent: Standardmodell-Anhänge in `~/.pi/agent` werden nicht gebunden, damit Pi-Schreibzugriffe in der Sandbox im Zustandsort landen; Pi kennt im Lauf die Nutzerwerte nicht. Doku in `docs/compatibility.md:62–69` und B4.md:84–98 übereinstimmend. Hinweis zur Präzision: „vibe setzt `--model` ausdrücklich“ gilt nur, wenn ein Modell konfiguriert ist (bin/vibe-run.sh:238, optional `--model`); ohne Modell fällt Pi auf den mit `auth.json` nicht hinterlegten Default zurück — sichtbare Fehlermeldung, kein stummer Fehlschlag. Der Kompromiss kann so stehen bleiben.
- Der Override einer umgebungsseitig gesetzten `PI_CODING_AGENT_DIR` ist bewusst und im Code (B4.md:57–60, bin/vibe_sandbox.py:576–579) dokumentiert; die Schreibgrenze bleibt deterministisch, keine Bedingungen oder Nutzerdurchlässigkeit.
- Argumentreihenfolge in `bwrap_argv()`: der neue Block (bin/vibe_sandbox.py:571–593) liegt nach den Geräte-`--dev-bind-try` (:562–563) und der opencode-`auth.json`-ro-Bind (:564–570), vor den XDG-Setenvs (:594–608); keine Wechselwirkung mit `--remount-ro /tmp` (:549–550), `.vibe`-ro-bind (:554–556) oder `/dev/shm` (:527–528), da der Pi-Ordner Teil des bereits früher gebundenen `state_path` ist (`--bind` :536–537).
- Testqualität der 6 Tests: gemeinsame `B4Fixture` (isoliertes `HOME` und Projekt in einem Tempordner unterhalb des Repositories, addCleanup räumt wieder auf), FUSE/NTFS-Beachtung (`expected_pi_dir` über Sandbox-Logik), Aufräumbeweis AK5 entfernt den Zustandsort im Testkörper vor der Restprüfung, verhindert zugleich das LIFO-Cleanup-Risiko; Digest-Attribution filtert fremde Sitzungen; keine Reihenfolgen- und gleitenden Abhängigkeiten von anderen Testklassen, keine Rabatte, keine `skip`-Marker — fehlendes bwrap führt zu festem FAIL (assertIsNotNone), passendes Bestand-Muster wie B5. Temporärordner (`.b4-*`) unter `REPO` werden per Cleanup entfernt, die Regeln des Projektordners sind damit nicht verletzt.

## Bestätigte Log-Einstiege

- `/tmp/opencode/vibe-sandbox/vibe-B4-a98BaT-174aaca080/tmp/b4-verify-full.log`: :5–7 (Quick-Anteile: Manifest 56 OK, Syntax OK, Geheimnisse OK), :103–109 (6× `test_b4_pi_agent_dir … ok`), :1800–1804 (Totals, Prüf-Exit 5)
- `/tmp/opencode/vibe-sandbox/vibe-B4-a98BaT-174aaca080/tmp/b4-baseline-verify.log`: :1830–1835 (1143/37/4, Exit 5)
- `b4-full-fails.txt` (38) vs. `b4-baseline-fails.txt` (41): Teilmengenabgleich selbst ausgeführt

## Verify-Abschnitt (des Reviewers)

- Change-Set: `11817c3..c139f84` (Ausgangscommit und Paket-Commit), Arbeitskopie sauber
- Git- und Lesekommandos selbst ausgeführt: `git status --short`, `git log --oneline -6`, `git diff 11817c3..c139f84 --stat/--numstat` und vollständige Diffs (bin/vibe_sandbox.py, docs/compatibility.md, docs/import-manifest.json, tests), Dateilesezugriffe auf bin/vibe_sandbox.py, bin/vibe_harness.py, bin/vibe-run.sh, alle drei B4-Dokumentate, FEEDBACK.md (B4-Abschnitt), tests/unit/test_b4_pi_agent_dir.py, tests/unit/test_sandbox.py (Auswahl), .vibe/project.env, .opencode/agents/test-agent.md. (Einzelne Git-Anfragen wie `git branch --show-current`/`git rev-parse` wurden von der Berechtigungseinstellung abgelehnt; die Branchzugehörigkeit ist dem Commitnamen entsprechend bestätigt.)
- Mitgeliefert und kritisch übernommen (nicht selbst ausgeführt): Rotphasenausgabe (failures=2, errors=3), echte Pi-Laufausgabe vor/nach dem Fix (EROFS-Abbruch vs. „No API key found“), Regressionssicherung „Ran 36 tests OK“ (test_sandbox + test_b5_sandbox). Keine Rückgabeartefakte; die Aussage, dass der Fehler vor dem Fix exakt dem B4-Defekt entspricht, steht im Kontrast zur logisch ableitbaren Rotphase aus dem Basestand (kein Pi-Block in 11817c3).
- Tests nicht unabhängig ausgeführt: alle Builds/Tests/Verify-Läufe (der Reviewer darf ausweislich der Regeln nicht selbst ausführen; die Verify-Protokolle wurden als Authentizitätsnachweis gelesen).
- Wichtige inspectierte Bereiche: Sandbox-Codepfad (state_dir, write_dirs, bwrap_argv, run), Pi-Harness (vibe_harness.py:322–334), Läuferkette (vibe-run.sh:228–256: bei `HARNESS=pi` läuft der Agentenaufruf tatsächlich unter `python3 bin/vibe_sandbox.py … --`), Manifest, alle drei Doku-Dokumente, FEEDBACK-Unverändertheit, Trilium-Prüfung (kein B4-Eintrag vorhanden — siehe Minor 1).
- Restrisken: der verbliebene falsche Harness-Kommentar (Medium 1) bis zur Korrektur; die textlichen Rotphasen-/Pi-Nachweise ohne Artefakte; die Umgebungs-Fails in verify.sh full (lifecycle/authorization Testsuite, Sandbox-Realtests) bestehen vom Basestand her und sind nicht durch B4 verursacht (beidseitig im Baseline bestätigt); Trilium-Eintrag noch offen (Minor 1), ist vor dem Abschluss-Commit zu erledigen.
