Ich habe den vollständigen Änderungssatz (`055cd71..Arbeitsstand` im Worktree `/tmp/opencode/vibe-git-rules`), den bereitgestellten Diff (574 Zeilen, inhaltlich mit meinem eigenen `git diff` übereinstimmend), die geänderten Quelldateien, Tests, Manifest und Dokumente gelesen. Da ich read-only bin, habe ich keine Tests ausgeführt; alle Testergebnisse sind daher Agentenangaben bzw. aus `docs/features/V-022.md` übernommen.

# Review result

**Verdict: CHANGES REQUIRED**

## Summary
- Critical: 0
- High: 0
- Medium: 2
- Minor: 2
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Alle Vorlagen und die Repository-`AGENTS.md` enthalten Feature-Branch-, Commit-, Diff-, Fremdänderungs- und History-Regeln | PASS (Implementierung), Testabdeckung nur teilweise → F-M1 | `templates/android/AGENTS.md:20`, `templates/docker/AGENTS.md:17`, `templates/generic/AGENTS.md:14`, `templates/openwrt/AGENTS.md:17`, `templates/rebuild/AGENTS.md:61`, `templates/web/AGENTS.md:17`, `AGENTS.md:82-96`, `bin/vibe:89-97` | `tests/unit/test_all_...` (`test_all_shipped_project_templates_contain_the_cleanup_rules`, :373-381) prüft pro Vorlage nur Marker, Cleanup-Überschrift, Git-Überschrift und `git status`; `test_general_rules_cover_cleanup_and_git_order` (:383-389) prüft die übrigen Regel-Familien nur gegen die Konstante, nicht gegen die Vorlagen. Läufe: nur vom Agenten geliefert (`Ran 19 tests / OK`, quick Exit 0) |
| `vibe init` aktualisiert einen vorhandenen verwalteten Block ohne umgebende Inhalte zu verändern | PASS (Agentenangaben) | `bin/vibe:1751-1761` (`ensure_general_rules` Update-Pfad), `bin/vibe:1773-1775` (Meldung „aktualisiert“) | `tests/unit/test_project_management.py:300` `test_init_updates_an_outdated_managed_rules_block_in_place` (Außeninhalt `## Eigener Rest` bewahrt, veralteter Inhalt entfernt); idempotenzseitig `test_init_does_not_duplicate_general_rules` (:290) und `test_init_on_an_already_prepared_project_changes_nothing` (:259, Byte-Vergleich). Rot-Phase und Läufe: nur Agentenangaben |
| Unpaarige Marker und Symlinks bleiben unangetastet | PASS (Agentenangaben) | `bin/vibe:1747` (islink-Abbruch), `bin/vibe:1753-1755` (Start ohne Ende → False ohne Schreibvorgang) | `test_init_leaves_an_unpaired_rules_marker_unchanged` (:320, Byte-Vergleich), `test_init_does_not_follow_an_agents_symlink` (:340, vorbestehend). Läufe: nur Agentenangaben |

Technische Plausibilität des Update-Pfads habe ich selbst nachvollzogen: Idempotenz (`updated == text` → False, `bin/vibe:1758`), konfliktgesichertes Schreiben via `vibe_storage` mit Digest (`bin/vibe:591-593`, `1749`), Verhalten bei „nur Endmarker“ (Zweig `added`, ungefährlich), mehrfacher Startmarker (nur erster ersetzt, harmlos). Der Manifest-Umfang (48 Einträge, u. a. `bin/vibe` und alle sechs `templates/*/AGENTS.md`) passt zur Agentenaussage „48 Dateien OK“.

## Findings
- [Medium] `tests/unit/test_project_management.py:373-389` — Vorlagenabdeckung deckt die Akzeptanzkriterien nur unvollständig
  - Evidence: Das Akzeptanzkriterium verlangt Feature-Branch-, Commit-, Diff-, Fremdänderungs- und History-Regeln in allen Vorlagen. Der templateglobale Test (`:373-381`) prüft je Vorlage nur Marker, „Projektordner sauber halten“, „Ordnung im Git halten“ und `git status`. „Feature-Branch“, „Force-Push“, die Diff- und die Fremdänderungsregel werden nur gegen die Konstante `GENERAL_RULES` (`:383-389`) geprüft. Die sechs Vorlagendateien sind separate Kopien; eine Vorlage könnte die History- oder Feature-Branch-Regel verlieren, ohne dass ein Test fehlschlägt. Implementierungsseitig sind die Regeln现实中 nachweislich in allen sechs Vorlagen vorhanden (eigene Prüfung per grep), der Befund betrifft allein die fehlende Absicherung.
  - Required fix: Vorlagetest stärken, z. B. in Schleife `self.assertIn(self.cli.GENERAL_RULES + "\n", text, path)` oder mindestens je zusätzlich `assertIn("Feature-Branch", text, path)` und `assertIn("Force-Push", text, path)`; danach alle Tests erneut ausführen und Ergebnis belegen.
- [Medium] `TICKETS.md:386,403-404`, `docs/features/V-022.md` — Trilium-Dokumentation fehlt, Abschlussnachweise unvollständig
  - Evidence: Das Projekt-`AGENTS.md` fordert „Diese Dokumentation zusätzlich über den vorhandenen Trilium-MCP-Zugang dokumentieren. Fehlt der Zugang, BLOCKIERT melden“ und die Definition of Done verlangt „Trilium-Dokumentation tatsächlich durchgeführt“. Der abgeschlossene V-021-Eintrag referenziert Trilium `TNxOZ5jYhTfI` (`TICKETS.md:384`); der V-022-Eintrag (bereits mit `[x]` abgehakt, `TICKETS.md:386`) nennt nirgendwo eine Trilium-Referenz, auch nicht in `docs/features/V-022.md`. Zusätzlich ist die V-022-Zeile „Review: `docs/reviews/V-022-review-1.md`“ (`TICKETS.md:403`) ungefüllt — die Datei existiert im Worktree nicht (mein glob), und die Hash-Korrektur „Commit: `6532aa5`“ liegt nur uncommitted im Arbeitsbaum vor.
  - Required fix: Trilium-Dokumentation für V-022 tatsächlich über den MCP-Zugang schreiben und die Notiz-ID in `TICKETS.md` nachtragen; Reviewdatei nach dieser Antwortinhalten unter `docs/reviews/V-022-review-1.md` speichern; erst nach finalem PASS die Commit-/Review-Nachweise in `TICKETS.md` einpflegen und zusammen mit diesem Paket committen (Arbeitsbaumänderung `M TICKETS.md` nicht verlieren).
- [Minor] `bin/vibe:549,1757-1764` — `_read_text` mit `errors="replace"` kann Nicht-UTF-8-Inhalte beim Block-Update still verändern
  - Evidence: `_read_text` liest mit `errors="replace"`. Im neuen Update-Pfad wird die komplette Datei mit dem ersetzten Text zurückgeschrieben; ungültige Bytes werden dadurch dauerhaft durch U+FFFD ersetzt statt unverändert erhalten. Vorbestehendes Verhalten des Helpers, aber durch die jetzt häufigere Vollplatz-Rewrite-Pfad ein etwas höheres Risiko. Praktisch gering, da `AGENTS.md`-Dateien Textdateien von Agenten sind; kein Test deckt es ab.
  - Required fix: Nicht blockierend — entweder dokumentieren, dass `AGENTS.md` UTF-8 sein muss, oder beim Vorhandensein von FFFE/ersetzten Zeichen das Update überspringen; ggf. mit einem Test absichern, der Binärbau-Bytes außerhalb des Blocks bis nach `vibe init` unverändert belässt.
- [Minor] `TICKETS.md:386` — Ticket vor Review-Abschluss mit `[x]` abgehakt
  - Evidence: Nach Arbeitsablauf Schritt 13 wird „erst dann [abhaken]: Ticket mit echten Nachweisen“, d. h. nach finalem PASS. Beim vorliegenden Stand (Review Runde 1 offen, Reviewdatei fehlt) ist das Häkchen vorgezogen. V-021 zeigt das erwartungsgemäße Format inklusive Reviewrunden und Trilium-Nachweis.
  - Required fix: Das Abhaken erst im Abschlusscommit vollziehen, zusammen mit Reviewpfad, Commit-ID und Trilium-Referenz.

## Verification
- Change set reviewed: `055cd71..working tree` im Worktree `/tmp/opencode/vibe-git-rules` (Branch `feature/v-022-general-git-rules`, Implementierungscommit `6532aa5`); dazu der synchron bereitgestellte Diff `/tmp/opencode/v022-review-diff.txt` (574 Zeilen, durch eigenes `git diff` bestätigt).
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git diff 055cd71 --stat`, `git diff -- TICKETS.md`; Inhaltsprüfung via grep/Read auf `bin/vibe`, `tests/unit/test_project_management.py`, `AGENTS.md`, `TICKETS.md`, `templates/*/AGENTS.md`, `docs/import-manifest.json`; glob auf `docs/reviews/V-022*` und `docs/features/V-022.md`.
- Checks with supplied output: unittest-Läufe (rot: 3 Failures, grün: `Ran 19 tests / OK`), `bash scripts/verify.sh quick` Exit 0, `full` Exit 0 in `/tmp/vibe-v022-full` (851 erkannt), `full`-Fehlschlag unter `/tmp/opencode` am Sandbox-Token-Test. Die 19 Testmethoden habe ich statisch nachzählend bestätigt (6 Discovery + 2 Roots + 9 Init + 2 TemplateRules = 19); 48 Manifesteinträge habe ich per grep-Zählung bestätigt.
- Checks not independently run: alle Build- und Testprüfungen (unittest, `verify.sh quick/full` inkl. Rot-Phase), Kontrolle der Manifestprüfsummen gegen Dateiinhalte, der `full`-Lauf-Sandbox-Kontext.
- Important areas inspected: `ensure_general_rules`/`cmd_init` (`bin/vibe:1735-1777`),konventionelle Konstante `GENERAL_RULES` samt neuer `GENERAL_RULES_END`, atomare Schreib-/Digest-Pfad (`bin/vibe:548-593`, `1749`), alle Vorlagenblöcke, Testdatei komplett, `docs/features/V-022.md`, `docs/import-manifest.json`.
- Remaining risks: Die Testergebnisse und Prüfsummen stammen vom Agenten und von `docs/features/V-022.md`, nicht aus独立 Quellen; die Begründung für den `full`-Fehler unter `/tmp/opencode` (V-021-Sandbox-Artefakt) habe ich nicht replizieren können; die noch offene Arbeitsbaumänderung `M TICKETS.md` und die heutige Reviewdatei müssen in den finalen Commit dieses Pakets.

Wichtigste Blocker für den finalen PASS sind dieselben zwei Medium-Befunde: Vorlagenabdeckung im Test ergänzen und die Trilium-Dokumentation inkl. Nachweisen in `TICKETS.md` fertigstellen.
