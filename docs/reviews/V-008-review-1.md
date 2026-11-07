# Review V-008 — Runde 1

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Gleiche Projektnamen eindeutig (mehrere Roots) | PASS | `bin/vibe:187-229` (`_project_rank`, `_project_key`, deterministische Sortierung nach Name → Root → Realpfad) | `tests/unit/test_project_management.py:117 test_duplicate_names_from_roots_with_equal_basenames_stay_unique` (3 eindeutige Keys, eindeutige Pfade); RoT-Phase plausibel: Altcode konnte bei drei Roots mit gleichem Basisnamen denselben Key `alpha@projects` doppelt vergeben (2 != 3) |
| Init erhält bestehende Dateien | PASS | `bin/vibe:922-944` (`copy_tree` mit `os.path.lexists`, überschreibt nie) | `tests/unit/test_project_management.py:229 test_init_keeps_existing_files_and_only_adds_missing_ones`, `:244 test_init_on_an_already_prepared_project_changes_nothing` (Byte-Vergleich vor/nach), `:263 test_init_does_not_write_through_a_broken_symlink` |
| Entfernen eines Roots löscht nichts | PASS | `bin/vibe:173-184` (`root_remove` schreibt ausschließlich CONF; kein Dateizugriff auf Projekte) | `tests/unit/test_project_management.py:191 test_removing_a_root_keeps_every_project_file`, `:205 test_removing_the_same_root_through_a_symlink_keeps_the_project` |
| Typen sind erweiterbar | PASS | `bin/vibe:912-920` (`types()` liest beliebige Ordner unter TPL, unverändert), `bin/vibe:940-946` | `tests/unit/test_project_management.py:274 test_init_applies_a_new_template_type_without_code_changes` |
| Tickets – Tests: Git-Verzeichnis und Git-Datei | PASS | `bin/vibe:191-203` (`.git` per `exists`, `.vibe` per `isdir`) | `tests/unit/test_project_management.py:107 test_git_directory_and_git_file_are_both_discovered` |
| Tickets – Tests: doppelte Namen | PASS | s. o. | s. o. |
| Tickets – Tests: Symlinks | PASS | `bin/vibe:131-144,150-184,216-229` | `:129 symlink_alias_inside_a_root...`, `:137 symlinked_root_is_not_scanned_twice`, `:205 ...through_a_symlink...` |
| Tickets – Tests: nicht lesbare Ordner | PASS | `bin/vibe:191-203` (`except OSError` um listdir/Stat-Zugriffe) | `:153 unreadable_project_folder...` und `:170 unreadable_root...` (ngestellter `PermissionError`, echte Codepfade) |
| Tickets – Tests: bereits vorbereitetes Projekt | PASS | s. o. | `tests/unit/test_project_management.py:244` |

## Findings
- [Minor] `tests/unit/test_project_management.py:191` — Testname/にDoku übertreibt die Assertion
  - Evidence: `test_removing_a_root_keeps_every_project_file` (und `docs/features/V-008.md:42` „ein Test vergleicht die Dateien vor und nach dem Entfernen") prüft de facto nur `wichtig.txt` und die Existenz der Verzeichnisse; hcodell ist das Kriterium stark abgesichert, weil `root_remove()` (bin/vibe:173-184) überhaupt keinen Projektzugriff macht.
  - Required fix: Dokumentation/Testnamen auf den tatsächlichen Nachweis (konfigurationsbezogenes Entfernen ohne Projektzugriff) zurechtstutzen oder die Assertion auf vollständiges Verzeichnisnetz erweitern.
- [Minor] `docs/features/V-008.md:38` — Aussage „Hinzufügen ... wirken auf die tatsächliche Wurzel, nicht auf einen Symlink-Namen" ist für `root_add` nicht ganz zutreffend: `root_add` speichert und gibt weiterhin den angegebenen (ggf. symlinkten) Pfad (`bin/vibe:153,168,171`), die Deduplication geschieht nur auf Realpfad-Ebene. Funational ist das vertretbar; die Formulierung überzeichnet.
  - Required fix: Formulierung in der Feature-Doku präzisieren (Deduplication über Realpfad, gespeicherter Pfad bleibt der angegebene).
- [Minor] `bin/vibe:103` — Neuer Key-Format `name@root` kann mit echten Verzeichnisnamen gleich normalisieren: `sess()`/`logpath()` normalisieren `@` → `_`, sodass z. B. Key `alpha@projects` und ein Projektordner `alpha_projects` dieselbe tmux-Sitzung und Logdatei teilen (`bin/vibe:603-604,861-871`). SPEC.md:191 („gleich normalisierte Namen ... keine Kollision") verlangt das eigentlich nicht; Colliderzeit erfordert aber drei genau passende Namen. Dasselbe Kollisionsmuster existierte bereits vorher (z. B. Ordner `a.b` vs. `a_b`).
  - Required fix: Beobachten; ggf. in einem späteren AP die Normalisierung für Lauf-IDs eindeutig machen (z. B. projektbezogene Laufkennung). Kein Blocker dieses Pakets.

## Verification
- Change set reviewed: Ausgangscommit `6eba342` (Branch `feature/v-008-projektverwaltung`) .. Arbeitsbaum. Shriff-Beschränkung: `shell`/Git cwdinentials sind in dieser Reviewer-Sitzung ohne Zugriff (%permission.rejected: shell%), daher konnte ich `git status --short` und `git diff 6eba342` nicht selbst ausführen. Ich habe den Branch direkt (`.git/HEAD` = `feature/v-008-projektverwaltung`), alle betroffenen Dateien vollständig gelesen bzw. gegen den fortlaufenden Auftrags diff abgeglichen, und der Wallterbaum enthält die beschriebenen Änderungen inhaltlich. Die Identität des Ausgangszustands (diff-faithful Altcode) kann ich aus dem fortlaufenden Auftrags diff und der konsistenten Rot-Phase-Sicht des Tests ableiten, nicht aus eigener Git-Ausführung.
- Git commands run by me: keine (Zugriff verweigert). Ersatzweise geprüft: `.git/HEAD`, `.git/logs/HEAD` (Checkout auf `feature/v-008-projektverwaltung` nach `6eba342`, noch keine Commits).
- Checks with supplied output: Unittest- (12 Tests OK; Rot-Phase mit 5 plausiblen, zum Altcode passenden Fehlern — ich habe die Altcode-Logik aus dem diff gegen die Testfehlermanewerten nachvollzogen: doppelte Key-Über schreibung, Nicht-Deduplizierung symlinkter Roots, Symlink-Folgen beim Init), `scripts/verify.sh quick`/`full` Exit 0 mit 476 Unit- + 34 Browser-Tests (476 = 464 aus V-007 + 12 neue — konsistent). Alle Prüfausdrucke stammen vom Coding-Agent, nicht von mir ausgeführt.
- Checks not independently run: alle Build- und Testchecks (shell verweigert); Unverfälschtheit von `scripts/verify.sh` / `$VIBE/_toolchain/verify` konnte ich ob der fehlenden Git-/Shellzugriffs gar nicht beurteilen.
- Important areas inspected: `bin/vibe` (Roots, Discovery, Init, copy_tree, cmd_new, cmd_roots), `tests/unit/test_project_management.py` (vollständig), `docs/features/V-008.md`, `docs/import-manifest.json` (V-008-Eintrag, Prüfsumme von bin/vibe aktualisiert), `docs/trilium-index.md:16`, Weboberfläche/Kompatibilität (`bin/vibe-web.py` `/api/roots|init|new` rufen `root_add`/`root_remove` unverändert, `ValueError` wird abgefangen — die Signaturen blieben gleich).
- Trilium: Notiz `SC3Jtp3csTnz` („V-008 Projektverwaltung und Vorlagen regressionssicher") existiert und wurde von mir gelesen; Inhalt deckt Ziel, Umsetzung, Tests und Grenzen des Pakets ab (eigene Prüfung, nicht Agentenangabe).
- Remaining risks: (1) SHA-Prüfsummen und Verify-Läufe sind nur Agentenangaben; (2) unbekannte weitere, nichts-dan unbemerkte Arbeitsbaumänderungen konnten ob der fehlenden `git status`-Ausführung nicht ausgeschlossen werden; vorbestehende Änderungen (`.vibe/project.env`, `SPEC.md`, PNGs) wurden wie beauftragt nicht geprüft; (3) das Normalisierung-Collision-Muster (Minor #3).

VERDICT: PASS — keine Critical-, High- und Medium-Befunde. Die Meritor-Beobachtungen sind dokumentative bzw. vorbestehend gleicher Klasse und blockieren nicht.
