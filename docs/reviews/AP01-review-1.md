# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3
- Verdict: PASS

## Acceptance criteria

| Kriterium | Status | Implementation (file:line) | Test / Nachweis |
|---|---|---|---|
| KISS als verpflichtendes Prinzip | PASS | `.ap01-wt/bin/vibe:97-102` (GENERAL_RULES), `AGENTS.md:97-100`, alle 6 `templates/*/AGENTS.md` (je Abschnitt „Leitlinien für Coding-Agenten (verbindlich)“) | `tests/unit/test_project_management.py:436-444` (`test_general_rules_require_kiss_clean_code_and_safe_caching`), `:427-435` (alle realen Vorlagendateien), `test_project_agents.py:470-471`; Green-Phase laut Agent: „Ran 7 tests / OK“ |
| Clean Code als verbindlicher Code-Stil | PASS | wie oben (bin/vibe:100, AGENTS.md, templates) | dieselben Tests; Assertions prüfen reale Dateiinhalte, nicht nur die Konstante |
| Caching nur mit funktionierender Invalidierung | PASS | bin/vibe:101 (Schlüssel, Lebensdauer, benannte Invalidierung, kein Caching ohne korrekte Invalidierung, keine ungeprüften Sicherheits-/Geheimnisdaten), AGENTS.md, templates | dieselben Tests (u. a. „Invalidierung“-Assertion) |
| Neue Projekte übernehmen Leitlinien | PASS | `templates/*/AGENTS.md` im verwalteten Block; `cmd_init`/`cmd_new` kopieren Vorlagen + `ensure_general_rules` (bin/vibe:1795, 1834-1835); Wortlaut „alle neuen und bestehenden Projekte“ in bin/vibe:102 | `test_all_shipped_project_templates_contain_the_coding_guidelines` (liest echte `templates/*/AGENTS.md`, schließt leere Trefferliste über `assertTrue(templates)` aus) |
| Bestehende Projekte automatisch übernommen | PASS | `cmd_init` ersetzt veralteten Block (bin/vibe:1753-1788); `cmd_run` aktualisiert vor jedem Lauf (bin/vibe:1528-1536), inkl. Weboberfläche (`vibe-web.py:304` ruft `cmd_run`); fail-closed bei Schreibfehlern (bin/vibe:1531-1534) | `test_init_replaces_an_outdated_rules_block...` (test_project_management.py:320-337), `test_cmd_run_updates_the_managed_rules_of_an_existing_project` (test_project_agents.py:454-471), `test_cmd_run_adds_the_rules_block_to_an_existing_project_without_one` (:473-486), `test_cmd_run_aborts_when_the_general_rules_cannot_be_updated` (:487-499, prüft SystemExit **und** `runner.assert_not_called()`) |
| Repository-AGENTS.md ebenfalls aktualisiert | PASS | `AGENTS.md:97-114` (Abschnitt vorhanden — durch die Sitzungseingabe unabhängig bestätigt) | `test_repository_agents_file_contains_the_coding_guidelines` (test_project_management.py:442-448) |

## Findings
- [Minor] `.ap01-wt/vibe-storage-locks-1000/`, `.verify-full.log` — Laufzeitartefakte im Worktree
  - Evidence: untracked Träger-/Log-Verzeichnisse aus den Prüfläufen liegen im Projektordner. Regel „Projektordner sauber halten“ verlangt Entfernung nach Abschluss; dürfen nicht committet werden (`.verify-full.log` ist gitignored, das Lock-Verzeichnis nicht).
  - Required fix: beide Laufzeitverzeichnisse vor dem Arbeitspaket-Commit aus dem Worktree entfernen bzw. Lock-Pfad konfigurieren (VIBE_STORAGE_LOCK_DIR), nicht committen.
- [Minor] `bin/vibe:1777-1778, 1765-1773` — Stille Auslassung bei nicht aktualisierbarem Block
  - Evidence: Unpaariger Marker, Nicht-UTF-8 oder fehlende/symlink-`AGENTS.md` liefern `False`; `vibe run` startet dann ohne Warnung mit veralteten bzw. ohne Leitlinien. Der Ticketwortlaut „verpflichtend/automatisch übernommen“ wird für diese Fälle nicht erfüllt. Es ist eine bewusste, in `docs/features/AP01.md:69-70` dokumentierte Schutzentscheidung (V-021/V-022-Verhalten, kein Überschreiben fremder Inhalte), daher nur Minor.
  - Required fix: Vor dem Start des Agentenlaufs in diesen Fällen eine Warnung nach `out` ausgeben („Leitlinien konnten nicht aktualisiert werden, bitte prüfen“), ohne das Verhalten der Schutzfälle zu ändern.
- [Minor] `bin/vibe:1531-1536` — Regelschreiben vor nachgelagerten Startprüfungen
  - Evidence: Die Aktualisierung läuft vor Sandbox-Check, Agent-/Modellprüfung und Pauseauswertung. Wenn der Start danach abbricht, wurde `AGENTS.md` bereits verändert, obwohl kein Lauf stattfindet. Beeinträchtigt keine fremden Inhalte und die Meldung fordert zur Prüfung/Commit auf; geringes Risiko.
  - Required fix: optional — Reihenfolge prüfen und Kommentar dazu im Code ergänzen, warum die Aktualisierung bewusst vor allen Startprüfungen erfolgt. Kein Codezwang, keine funktionale Änderung erforderlich.

## Verification
- Change set reviewed: Worktree `.ap01-wt`, Branch `feature/ap01-coding-agent-guidelines-final`, Ausgangscommit `8b2cc3f..working tree` (13 geänderte + 1 neue Untracked-Datei `docs/features/AP01.md`); vollständiger `git diff` gelesen, Untracked-Datei vollständig gelesen. Kein AP01-Commit vorhanden — gemäß Arbeitsablauf (Schritt 13) erwartet.
- Git commands run by me: `git -C .ap01-wt status --short`, `rev-parse HEAD`, `branch --show-current`, `log --oneline -3`, `git diff --stat`, `git diff -- AGENTS.md TICKETS.md docs/ templates/`, `git diff -- bin/vibe tests/`.
- Ergänzende unabhängige Nachweise (nur Lesen): `ensure_general_rules`-Implementation samt Schutzpfaden (Symlink-Abbruch bin/vibe:1765, Not-UTF-8-fail-safe :1771-1773, unpaariger Marker :1776-1778, TOCTOU-Schutz über `file_digest` + `_write_text_atomic` → `vibe_storage.write_bytes` mit erwarteter Prüfsumme, `ConcurrentChangeError` ist `StorageError` und wird daher catched); Aufrufpfade (TEMPLATES ohne `common/AGENTS.md`; Weboberfläche ruft `cmd_run`); Tests vollständig gelesen — alle 7 neuen Tests sind echte Verhaltensprüfungen mit realem Dateischreiben und resultierenden Dateiinhalten, Mocking nur der Laufumgebung, bestehende Tests nur ergänzt, keine skip/Ignore, keine geschwächten Assertions; `scripts/verify.sh` und Prüftoolchain vom Change set unberührt; Manifest-Diff enthält genau die 7 geänderten Programmdateien + AP01-Eintrag; Trilium-Notiz `B34A8yyWkjCo` „AP01 Leitlinien für Coding-Agenten“ über MCP unabhängig gelesen — existiert, Inhalt deckt fachliche Umsetzung, Red/Green- und Prüfnachweise ab; `docs/trilium-index.md` Eintrag konsistent.
- Checks with supplied output (vom Coding-Agent berichtet, von mir nicht unabhängig ausgeführt): Red-Phase (7 Tests: 6 failures + 1 error gegen 8b2cc3f), Green-Phase (7 Tests OK), `verify.sh quick` Exit 0 (53 Manifestdateien, Syntaxchecks, Geheimnisprüfung), `verify.sh full` in Bubblewrap-Umgebung Exit 0 (863+58 Tests, „OK: Tests erkannt: 921“). Die Begründung der bwrap-Umgebungsanpassung (`SANDBOX`-Erbe, schreibgeschütztes `/tmp`) ist in `docs/features/AP01.md:132-156` dokumentiert und inhaltlich plausibel; die Umgebungsvariable wird entfernt, nicht das Prüfskript geändert.
- Checks not independently run: alle Build-/Testläufe, `verify.sh` quick/full, Neuberechnung der SHA-256 im Manifest (nicht-Git-Befehle sind mir nicht erlaubt); die Prüfsummen sind therefore agent-reported, nicht unabhängig verifiziert. Das genaue Zustandekommen des „1 error“ in der Red-Phase habe ich nicht nachvollzogen (Detail ohne Auswirkung auf das Ergebnis).
- Important areas inspected: `bin/vibe` (GENERAL_RULES, cmd_run, ensure_general_rules, cmd_init/cmd_new, `_write_text_atomic`), `bin/vibe_storage.py` (write_bytes/file_digest/StorageError-Hierarchie), `tests/unit/test_project_agents.py`, `tests/unit/test_project_management.py`, alle Template-AGENTS.md, Root-`AGENTS.md`, `docs/import-manifest.json`, `docs/features/AP01.md`, `docs/trilium-index.md`, `TICKETS.md`, `vibe-web.py` (Aufrufpfad).
- Remaining risks: Manifest-Prüfsummen und Testläufe nur agent-reported; als Randfall bleiben Projekte mit unpaarigem Marker/Not-UTF-8 ohne Leitlinien (dokumentierter Abwägungspunkt); die Laufzeitverzeichnisse im Worktree müssen vor dem Commit entfernt werden.
