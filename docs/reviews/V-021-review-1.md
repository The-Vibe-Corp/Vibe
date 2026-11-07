# Review V-021 — Runde 1

Reviewer: code-reviewer
Worktree: /tmp/opencode/vibe-installer-autonomous
Basis: f245113, Commits 9d7f17d und a5606f8
Diff: /tmp/opencode/v021-review-diff.txt (714 Zeilen)

Hinweis: Der erste Reviewdurchlauf erreichte das Schrittlimit und endete mit
einer vorläufigen Einschätzung. Die anschließende fokussierte Nachprüfung
derselben Sitzung schloss das Review ab. Die abschließende Antwort wird
unverändert wiedergegeben.

---

# Review Result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: **PASS**

## Acceptance Criteria
| Criterion | Status | Evidence |
|---|---|---|
| Setup installiert jedes vom Startbefehl importierte Modul (inkl. `vibe_autonomous.py`) | PASS | `PROGRAM_FILES` in `scripts/setup-vibe.py:30-45` enthält alle 9 von `bin/vibe` importierten Module; `test_every_module_imported_by_the_launcher_is_installed` grün |
| Regressionstest leitet benötigte Module aus `bin/vibe` ab und startet installierte CLI | PASS | `launcher_sibling_modules()` in `tests/unit/test_setup_vibe.py:44-58` nutzt AST; `test_installed_launcher_starts_with_all_options` führt `vibe types` aus |
| Alle mitgelieferten Projektvorlagen enthalten Aufräumregeln | PASS | 6 Templates (`templates/*/AGENTS.md`) haben Marker `<!-- vibe:general-rules -->` und Text "Projektordner sauber halten" |
| `vibe init` ergänzt Regeln in vorhandener `AGENTS.md` genau einmal, lässt Inhalte/Symlinks unverändert | PASS | `ensure_general_rules` in `bin/vibe:1726-1743` prüft Marker, Symlink (`os.path.islink`), nutzt atomaren Write mit Checksumme; Tests `test_init_appends_general_rules...`, `test_init_does_not_duplicate...`, `test_init_does_not_follow_an_agents_symlink` grün |
| Tests `test_setup_vibe.py`, `test_project_management.py`, `verify.sh quick/full` grün | PASS | Alle 47+16 Unit-Tests OK; `bash scripts/verify.sh quick` Exit 0; `full` in sauberer Umgebung Exit 0 |
| Dokumentation `docs/features/V-021.md` und Trilium, Ticket V-021 aktualisiert | PASS | `docs/features/V-021.md` vollständig; `TICKETS.md:362-375` enthält Ticket; `docs/import-manifest.json` aktualisiert |

## Findings

### [Minor] `AGENTS.md:71-80` vs `bin/vibe:84-87` — Aufräumregel-Wortlaut in Root-AGENTS.md und verwaltetem Block weichen ab
- **Evidence**: Root-AGENTS.md enthält "Screenshots ohne Nachweiswert", "entfernen; nicht committen" (Semikolon), "stashen" und zusätzlichen Punkt "Laufzeitdaten, persönliche Konfiguration und Geheimnisse". Der verwaltete Block in `GENERAL_RULES` (Templates + `ensure_general_rules`) ist knapper: "entfernen und nicht committen", kein "stashen", kein Extrapunkt.
- **Required fix**: Keine funktionale Korrektur nötig; Dokumentation in `docs/features/V-021.md` nennt bereits "ausführlicher in der AGENTS.md dieses Repositorys". Optional: `GENERAL_RULES` in `bin/vibe:81-88` an Root-AGENTS.md angleichen, um Verwirrung zu vermeiden.

### [Minor] `docs/features/V-021.md:152-154` — Bekannte Grenze erwähnt `vibe-web.py` als anderen Einstieg, nennt aber nicht explizit, dass `vibe_guide.py` und `vibe-web.py` aktuell in `PROGRAM_FILES` sind, ohne von `bin/vibe` importiert zu werden
- **Evidence**: `PROGRAM_FILES` in `scripts/setup-vibe.py:34,41` enthält `vibe-web.py` und `vibe_guide.py`; AST-Test in `tests/unit/test_setup_vibe.py:44-58` findet diese nicht (nur Importe aus `bin/vibe`). Doku-Zeile 153 sagt "Importiert ein künftiges Modul ausschließlich aus `vibe-web.py` …", impliziert aber nicht, dass dies *aktuell* der Fall ist.
- **Required fix**: In `docs/features/V-021.md` Grenzbeschreibung präzisieren: "Aktuell werden `vibe_guide.py` und `vibe-web.py` installiert, ohne von `bin/vibe` importiert zu sein (andere Einstiegspunkte). Der Test prüft nur `bin/vibe`."

## Verification
- **Change set reviewed**: `f245113..HEAD` (Commits `9d7f17d`, `a5606f8`) im Worktree `/tmp/opencode/vibe-installer-autonomous`
- **Checks with supplied output**:
  - `python3 -m unittest tests.unit.test_setup_vibe -v` → 47 OK
  - `python3 -m unittest tests.unit.test_project_management -v` → 16 OK
  - `bash scripts/verify.sh quick` → Exit 0
- **Checks not independently run**: `bash scripts/verify.sh full` (behauptet Exit 0 in `/tmp/vibe-v021-full`; Umgebungsartefakt `test_real_sandbox_allows_questions_but_not_the_web_token` auf `f245113` reproduzierbar, nicht Paket-bedingt)
- **Important areas inspected**: `scripts/setup-vibe.py`, `bin/vibe` (`ensure_general_rules`, `PROGRAM_FILES`, Imports), `templates/*/AGENTS.md`, `tests/unit/test_setup_vibe.py`, `tests/unit/test_project_management.py`, `docs/features/V-021.md`, `TICKETS.md`, `docs/import-manifest.json`
- **Remaining risks**: Keine für dieses Arbeitspaket. Die beiden Minor-Befunde sind rein dokumentarisch/konsistenzbezogen, keine funktionalen Mängel.
