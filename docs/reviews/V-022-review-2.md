Alle Fakten sind beisammen. Abschließende Bewertung:

- **Befund 1 (Vorlagenabdeckung):** behoben — `tests/unit/test_project_management.py:382-398` prüft jetzt pro Vorlage zusätzlich den exakten `GENERAL_RULES`-Block (`assertIn(self.cli.GENERAL_RULES, text, path)`, erfordert Byte-identische Blöcke in allen Vorlagen, von mir stichprobenartig gegen `templates/generic/AGENTS.md` und `bin/vibe:82-97` bestätigt) sowie die Regelarten Feature-Branch, git status, Diff, stashen, Force-Push. Würde-rot-Behauptung ist plausibel, aber nur Agentenangabe.
- **Befund 2 (Trilium):** von mir unabhängig über `get_note` verifiziert — Notiz `0nTTx7KSysUQ` existiert, Parent `IjRpjYJTtqam`, Inhalt enthält Git-Regeln, Commit `6532aa5`, Reviewverweis. Kleine Unstimmigkeit: Notiz nennt noch „795 Unit-/851 erkannt“ statt 796/852.
- **Befund 3 (Nicht-UTF-8):** `bin/vibe:1750-1755` liest strikt UTF-8 und bricht vor jeder Schreibvorgang ab; Test `:329` vergleicht Bytes. Kein neuer Seiteneffekt: `_read_text` (`:548-549`) nutzte bereits Textmodus mit universellen Newlines; einziger Verhaltensunterschied ist das Wegfallen von `errors="replace"`.
- **Befund 4 (Abhaken):** `TICKETS.md:386` steht wieder auf `[ ]`, Nachweise (Commit, Prüfungen, Review, Trilium) sind eingetragen.

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Alle mitgelieferten Vorlagen und die Repository-`AGENTS.md` enthalten Feature-Branch-, Commit-, Diff-, Fremdänderungs- und History-Regeln | PASS | `bin/vibe:82-97`, `AGENTS.md:82-95`, `templates/android/AGENTS.md:20`, `templates/docker/AGENTS.md:17`, `templates/generic/AGENTS.md:14`, `templates/openwrt/AGENTS.md:17`, `templates/rebuild/AGENTS.md:61`, `templates/web/AGENTS.md:17` | `tests/unit/test_project_management.py:382-398` (`test_all_shipped_project_templates_contain_the_cleanup_rules`: je Vorlage exakter `GENERAL_RULES`-Block plus 7 Regel-Assertions) und `:400` (`test_general_rules_cover_cleanup_and_git_order`). Blockgleichheit der Vorlagen mit der Konstante zusätzlich von mir stichprobenartig per Read verifiziert. Testläufe: nur vom Agenten geliefert (`Ran 20 tests / OK`) |
| `vibe init` aktualisiert einen vorhandenen verwalteten Block ohne umgebende Inhalte zu verändern | PASS | `bin/vibe:1756-1766` (Update-Pfad), `bin/vibe:1778-1780` (Meldung „aktualisiert“/„ergänzt“) | `test_init_updates_an_outdated_managed_rules_block_in_place` (`:300`, Außeninhalt `## Eigener Rest` bewahrt, veralteter Inhalt entfernt, genau eine Markierung); Idempotenz `:259`, `:290`. Läufe: nur Agentenangaben |
| Unpaarige Marker und Symlinks bleiben unangetastet | PASS | `bin/vibe:1747` (islink-Abbruch), `bin/vibe:1758-1760` (Start ohne Ende → Rückgabe ohne Schreibvorgang) | `test_init_leaves_an_unpaired_rules_marker_unchanged` (`:320`, Byte-Vergleich), `test_init_does_not_write_through_a_broken_symlink` (`:338`), `test_init_does_not_follow_an_agents_symlink` (`:349`). Läufe: nur Agentenangaben |
| (Nachbesserung Runde 1) Nicht-UTF-8-`AGENTS.md` bleibt unverändert | PASS | `bin/vibe:1750-1755` (strikt UTF-8, `UnicodeDecodeError` → Rückgabe vor jeder Erlaubnine auf Schreiben) | `test_init_leaves_non_utf8_agents_file_unchanged` (`:329`, Byte-Vergleich). Rot-Phase: nur Agentenangabe (`AssertionError: b'...\xef\xbf\xbd...' != b'...\xff...'` in `docs/features/V-022.md`) |
| (Nachbesserung Runde 1) Trilium-Dokumentation vorhanden | PASS | Trilium-Notiz `0nTTx7KSysUQ` (Parent `IjRpjYJTtqam`), referenziert in `TICKETS.md` (V-022-Eintrag) | `docs/reviews/V-022-review-1.md` gespeichert (von mir gelesen), Notiz-Existenz und -Inhalt von mir unabhängig per `get_note` verifiziert |
| (Nachbesserung Runde 1) Ticket erst nach finalem PASS abhaken | PASS | `TICKETS.md:386` (`[ ]`) | Nachweis in `TICKETS.md` vollständig eingetragen (Commit, Prüfungen, Reviewpfad, Trilium-ID) |

## Findings
- [Minor] Trilium-Notiz `0nTTx7KSysUQ` (Tests-Abschnitt) — veraltete Prüfergebniszahlen in der Trilium-Dokumentation
  - Evidence: Die Notiz nennt „795 Unit- + 56 Browser-Tests, 851 erkannt“, entspricht dem Stand vor dem Nicht-UTF-8-Test; TICKETS und `docs/features/V-022.md` nennen korrekt 796/852. Reine Dokumentationsstale, kein Codebeeinfluss.
  - Required fix: Beim Abschlusscommit die Testzahlen in der Trilium-Notiz auf 796/852 bzw. den finalen Stand aktualisieren (durch den Coding-Agenten, nicht vom Reviewer).
- [Minor] `tests/unit/test_project_management.py:382-398` — Repository-`AGENTS.md` ohne automatisierte Absicherung
  - Evidence: Das Akzeptanzkriterium umfasst auch die Repository-`AGENTS.md`. Sie ist in `docs/import-manifest.json` nicht erfasst (nur `templates/*/AGENTS.md` und `bin/vibe`) und wird von keinem Test geprüft; der Inhalt ist aktuell korrekt (`AGENTS.md:82-95`, eigenes Read). Ein späteres versehentliches Entfernen des Blocks würde keinen Test rot machen.
  - Required fix: Nicht blockierend — z. B. `AGENTS.md` in die Manifest-Prüfsummenprüfung aufnehmen (dann beim Folgeanlass der Hashaktualisierungsmitieren beachten) oder den Vorlagetest um die Repository-Wurzel erweitern.

## Verification
- Change set reviewed: `055cd71..working tree` im Worktree `/tmp/opencode/vibe-git-rules` (Implementierungscommit `6532aa5`, dazu uncommitted Nachbesserungen auf `branch feature/v-022-general-git-rules`); bereitgestellter Diff `/tmp/opencode/v022-review2-diff.txt` (621 Zeilen) gegen eigenen `git diff` abgeglichen — inhaltlich identisch abgedeckt.
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git diff 055cd71..HEAD --stat`, `git diff --stat`, `git diff` (Arbeitsbaum).
- Checks with supplied output: unittest-Läufe (rot: 3 Failures, grün: `Ran 20 tests / OK`; UTF-8-Test rot separat dokumentiert), `verify.sh quick` Exit 0 (48 Manifestdateien), `verify.sh full` Exit 0 in `/tmp/vibe-v022-full` (796/852) — alle vom Coding-Agenten geliefert und in `docs/features/V-022.md` niedergeschrieben, nicht von mir ausgeführt bzw. nicht von mir replizierbar (Read-only).
- Checks not independently run: alle Build-, Unit-, Browser- und Manifest-Prüfsummen-Läufe; die Rot-Phasen; das Verhalten von `full` unter `/tmp/opencode` betreffend Sandbox-Token-Artefakt.
- Important areas inspected: `ensure_general_rules`/`cmd_init`/`_read_text`/`_write_text_atomic`-Pfad (`bin/vibe:548-549, 591, 80-97, 1735-1782`), zweiter Aufrufer `cmd_new` (`bin/vibe:1815`), alle neun geänderten Feedback-Dateien, Testdatei komplett (20 Testmethoden, keine Skip-Marker, alle mit Assertions), `docs/import-manifest.json` (Manifest erfasst V-022-Änderungen korrekt, `AGENTS.md` nicht enthalten — siehe Minor), `TICKETS.md`, `docs/features/V-022.md` inkl. Red-Green-Dokumentation, `docs/reviews/V-022-review-1.md`, Trilium-Notiz über MCP.
- Remaining risks: Alle Test- und Rot-Phasen-evidenzen sind Agentenangaben, die inhaltlich plausibel (Testzahlen, Fehlermeldungen) und in `docs/features/V-022.md` dokumentiert sind; ich habe sie nicht eigenständig ausgeführt. Die Manifest-Prüfsummen für `bin/vibe` habe ich nicht selbst gehasht (Read-only, nur Git-Kommandos). Für den finalen Abschlusscommit verbleiben die uncommitted Änderungen (Nachbesserungen, TICKETS-Nachweise, Reviewdatei), die zusammen mit diesem PASS committet werden müssen — danach gilt der Verfahrenspunkt „keine Implementierungsänderungen ohne erneuten Review“.

Verdict: PASS unter Vorbehalt den fortgeschriften Nachweisabkommens — die zwei Minor-Befunde blockieren den PASS nach den Projektregeln („keine offenen Critical/High/Medium-Befunde“) nicht; Fortbesteh der Prüfpflicht bleibt unberührt.
