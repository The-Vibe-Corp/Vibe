# Review AP4-Korbat — Runde 2

- **Ticket:** AP4-Korbat — Work package closing process rework for GitHub-connected projects
- **Ausgangscommit:** `212d97d` (auf Branch `feature/korbat/ap4-korbat`)
- **Delta-Runde 2:** Nachbesserung der 3 Minor-Befunde aus `docs/reviews/AP4-Korbat-review-1.md` (`bin/vibe`, `bin/vibe-web.py`, `bin/web/nova-project.js`, `docs/import-manifest.json`) sowie Regressionsschutz durch den unabhängigen Test-Agenten (`tests/unit/test_ap4_korbat_gui.py`, `tests/unit/test_ap4_korbat_worktrees_sessions.py`, `tests/unit/test_ap4_korbat_github.py`, `docs/reviews/AP4-Korbat-test-agent-report.md` §10).
- **Datum:** 2026-11-21
- **Reviewer:** Unabhängiger Review-Agent (Read-only)

---

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

---

## 1. Behebungsurteil zu den drei Runde-1-Befunden

| Runde-1-Befund | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| **B1**: `POST /api/sessions` mit `action: "continue"` reicht `resume_package`/`resume_worktree`/`resume_branch` defensiv aus dem Session-Registry-Eintrag an `vibe.cmd_run` weiter; ohne Anhang bleibt es beim reinen Continue | **erfüllt (PASS)** | `bin/vibe-web.py:1573-1585` (`resume_package = str(entry.get("package_id") or "").strip() or None`, analog `resume_worktree` und `resume_branch`, Übergabe an `vibe.cmd_run`) | `tests/unit/test_ap4_korbat_gui.py:284-356` (`SessionsContinueResumePackageTest`: `test_continue_exports_the_resume_package_and_worktree` + `test_continue_without_attachment_stays_plain_continue`) — grün im gelieferten Prüfnachweis (`Ran 41, OK`) |
| **B1 (Optionale Ergänzung)**: `bin/web/nova-project.js` Überblicks-Tab zeigt den Paket-/Worktree-Anhang der Session analog zu `nvpSessionsSection` | **erfüllt (PASS)** | `bin/web/nova-project.js:1006-1015` (`el('span', {class: 'nv-muted', 'data-nv-session-attach': ''}, (row.package_id \|\| row.worktree_path) ? tr('Paket ') + String(row.package_id \|\| '?') + tr(' · Arbeitskopie ') + String(row.worktree_path \|\| '?') : '')`) — exakt analog zu `nvpSessionsSection` in `bin/web/nova-project.js:524-527` | Statische Inspektion von `bin/web/nova-project.js:522-531,1006-1015` + `tests/unit/test_ap4_korbat_gui.py` (`Ran 41, OK`) |
| **B2**: `bin/vibe` sichert `resume_worktree` und `resume_branch` im tmux-Startbefehl mit `shlex.quote(...)` ab; harte Zeichenklassenprüfung für `continue_session`/`resume_package` bleibt erhalten | **erfüllt (PASS)** | `bin/vibe:51` (`import ... shlex ...`), `bin/vibe:1956-1962` (`re.fullmatch(r"[A-Za-z0-9_-]+", ...)` für `continue_session` und `resume_package`), `bin/vibe:2074-2080` (`shlex.quote(resume_worktree)` und `shlex.quote(resume_branch)`) | `tests/unit/test_ap4_korbat_worktrees_sessions.py:807-843` (`SessionResumeHintsTest.test_resume_hints_are_quoted_for_the_shell`) — grün im gelieferten Prüfnachweis (`Ran 41, OK`) |
| **B3**: `bin/vibe` `cmd_github` Status-Zweig gibt eine Zeile „Auto-Merge: ja/nein (…)" aus `st["auto_merge"]` aus (Übereinstimmung mit `docs/features/AP4-Korbat.md:113`) | **erfüllt (PASS)** | `bin/vibe:1184-1186` (`line("Auto-Merge:", "ja (Läufer mergt freigegebene Merge-Requests selbst)" if st["auto_merge"] else "nein (PR-only: Eigentümer mergt und schließt mit 'vibe package close')")`) | `tests/unit/test_ap4_korbat_github.py:566-630` (`GithubCliStatusTest`: `test_status_names_auto_merge_ja_when_enabled` + `test_status_names_auto_merge_nein_when_disabled`) — grün im gelieferten Prüfnachweis (`Ran 19, OK`) |

---

## 2. Regressionsschutz des Test-Agenten (Prüfpunkt 2)

- **Neue Testfälle durch den unabhängigen Test-Agenten (5 neue Methoden, Gesamtbestand AP4 jetzt 71 Fälle statt 66):**
  1. `tests/unit/test_ap4_korbat_gui.py:284-356` — `SessionsContinueResumePackageTest`:
     - `test_continue_exports_the_resume_package_and_worktree` (Zeilen 313–337): prüft über den echten HTTP-Handler (`POST /api/sessions`, `action="continue"`) und die aufzeichnende tmux-Attrappe, dass `VIBE_CONTINUE_SESSION` (`ses_wt`), `VIBE_RESUME_PACKAGE` (`F1`), `VIBE_RESUME_WORKTREE` (`<worktree>`) und `VIBE_RESUME_BRANCH` (`feature/test/f1`) im Startbefehl exportiert werden.
     - `test_continue_without_attachment_stays_plain_continue` (Zeilen 339–356): prüft für einen Session-Eintrag ohne Worktree-Anhang, dass `VIBE_CONTINUE_SESSION` (`ses_plain`) gesetzt wird und alle drei `VIBE_RESUME_*`-Variablen leer (`[]`) bleiben.
  2. `tests/unit/test_ap4_korbat_worktrees_sessions.py:807-843` — `SessionResumeHintsTest.test_resume_hints_are_quoted_for_the_shell`:
     - Übergibt einen Worktree-Pfad mit Leerzeichen (`worktrees/x y`) und einen Branch mit Semikolon und Leerzeichen (`feature/test/f1;echo PWNED`) über `vibe sessions resume proj --session ses_q`.
     - Prüft scharf, dass `shlex.quote(str(worktree))` und `shlex.quote(branch)` im aufgezeichneten tmux-Befehl stehen, dass der ungeschützte String `"VIBE_RESUME_BRANCH=" + branch + ";"` **nicht** vorkommt und dass `self.exports("VIBE_RESUME_PACKAGE")` weiterhin `["F1"]` liefert.
  3. `tests/unit/test_ap4_korbat_github.py:566-630` — `GithubCliStatusTest`:
     - `test_status_names_auto_merge_ja_when_enabled` (Zeilen 608–618) und `test_status_names_auto_merge_nein_when_disabled` (Zeilen 620–630): rufen `cmd_github("proj", "status", out=out)` mit `GITHUB_AUTO_MERGE="1"` bzw. `""` auf und prüfen die ausgegebene `Auto-Merge:`-Zeile auf `"ja"` bzw. `"nein"`.
- **Keine Abschwächung bestehender Tests:** Alle 66 Testfälle aus Runde 1 sowie die Bestandsmodule (`test_ap19_sessions_api`, `test_f25_session_continue`) sind unverändert und ungeschwächt erhalten.
- **Dokumentation im Test-Agent-Bericht:** Alle fünf neuen Fälle sind mit Vorbedingung, Aktion, Erwartung, Fehlerfall und Nachlauf-Ergebnissen vollständig in `docs/reviews/AP4-Korbat-test-agent-report.md:443-518` (Abschnitt 10, Unterabschnitte 10.1–10.4) dokumentiert.

---

## 3. Prüfung auf Nebenwirkungen / neuen Schaden durch die Fixes (Prüfpunkt 3)

- **`bin/vibe-web.py`:**
  - Der Guard- und Validierungsfluss vor `/api/sessions` ist unangetastet: `known(name)` wird weiterhin vor dem Handler geprüft; die Prüfungen auf `action != "continue"`, Projektzugehörigkeit des Session-Eintrags, `run_is_active(name)` und `session_resume_supported()` laufen unverändert vor dem `else`-Zweig.
  - Da `not entry` bereits vorher abgefangen wird, ist `entry` im Resume-Zweig garantiert ein `dict`. Fehlende oder leere Felder (`package_id`, `worktree_path`, `branch`) werden über `str(entry.get(...) or "").strip() or None` sauber auf `None` abgebildet, sodass bestehende AP19-/F25-Aufrufe ohne Worktree-Anhang exakt wie zuvor funktionieren (belegt durch `test_ap19_sessions_api` + `test_f25_session_continue`: Ran 33, OK).
- **`bin/vibe`:**
  - `shlex` war bereits importiert; kein neuer Import nötig.
  - Die harte Zeichenklassenprüfung (`re.fullmatch(r"[A-Za-z0-9_-]+", ...)`) für `continue_session` und `resume_package` ist unverändert aktiv.
  - Für einfache Pfade und Branchnamen aus `[A-Za-z0-9_./-]` gibt `shlex.quote` den String ohne Anführungszeichen zurück, sodass bestehende Parser und Tests kompatibel bleiben; bei Leer- oder Sonderzeichen schützt `shlex.quote` zuverlässig vor Worttrennung und Befehlsinjektion in `bash -lc`.
- **`bin/web/nova-project.js` & `bin/web/nova-settings.js`:**
  - Der Überblicks-Session-Anhang nutzt ausschließlich das sichere DOM-only-Helfermuster `el('span', ..., String(...))` (kein `innerHTML`).
  - Kein Token gelangt in den DOM (`nvpGithubSection` zeigt weiterhin nur `g.auth.source`).
  - `bin/web/nova-settings.js` ist unverändert; alle Feature-Defaults bleiben gemäß Nutzerentscheidung Option B aus.
- **`docs/import-manifest.json`:**
  - Enthält einen eigenen, sauber begründeten Änderungseintrag für `AP4-Korbat` (Review-Runde 1) mit den geänderten Dateien `bin/vibe`, `bin/vibe-web.py`, `bin/web/nova-project.js` und `docs/import-manifest.json`.
  - Die `files`-Einträge für `bin/vibe` (`291967` Bytes, SHA-256 `a4df9352...`), `bin/vibe-web.py` (`116517` Bytes, SHA-256 `70452e81...`) und `bin/web/nova-project.js` (`49197` Bytes, SHA-256 `2ad5f052...`) sind aktualisiert und im gelieferten Prüfnachweis durch `python3 scripts/check-import-manifest.py` (`OK (67 Dateien)`) bestätigt.

---

## 4. Gesamtbestätigung der Runde-1-Kernelemente (Prüfpunkt 4)

Stichprobenartiger Abgleich gegen die Runde-1-Belege bestätigt, dass alle Kernelemente unverändert intakt sind:
- **Runner-Abschlussfolge (`bin/vibe-run.sh:1624-1715`):** `ensure_mergeable_package` → `github-complete` → `worktree-register` Upsert → Verzweigung nach `PR_URL` und `GITHUB_AUTO_MERGE` (PR-only-Standard ohne lokalen Merge mit `pr_only_fallback`; Auto-Merge mit Squash-Merge per REST, genau einem begrenzten Konflikt-Reparaturdurchlauf bei RC=2, `github-pull`, `finish_closed_package` und `sessions-forget-worktree`; lokaler Fallback ohne GitHub).
- **SPEC.md & GENERAL_RULES (`SPEC.md:330,343-372`, `bin/vibe:101-144`, `templates/*/AGENTS.md`):** Einziger kanonischer Abschnitt `## Git & work-package closing (runner-owned)` in `SPEC.md`, genau ein Markerpaar in `GENERAL_RULES`, `## Laufende Instanz nicht verändern (verbindlich)` genau 1× in `bin/vibe:120-122` und bytengleich in allen 5 Vorlagen.
- **Option B & Descoping T-G6:** `bin/web/nova-settings.js` und `tests/browser/test_ap22_settings_ui.py` unberührt; T-G6 wie beauftragt descoped und in `docs/features/AP4-Korbat.md` ausgewiesen; vom Nutzer selbst vorzunehmende Schritte in `docs/features/AP4-Korbat.md` vollständig gelistet.

---

## Findings

- Keine Befunde (Critical: 0, High: 0, Medium: 0, Low/Minor: 0, Info: 0). Alle drei Minor-Befunde aus Runde 1 sind vollständig und rückstandsfrei behoben.

---

## Verification

- **Change set reviewed:** `212d97d..working tree` einschl. Delta der Runde 2 (`bin/vibe`, `bin/vibe-web.py`, `bin/web/nova-project.js`, `docs/import-manifest.json`, `tests/unit/test_ap4_korbat_gui.py`, `tests/unit/test_ap4_korbat_worktrees_sessions.py`, `tests/unit/test_ap4_korbat_github.py`, `docs/reviews/AP4-Korbat-test-agent-report.md`, `docs/reviews/AP4-Korbat-review-1.md`, `docs/features/AP4-Korbat.md`, `bin/vibe-run.sh`, `bin/web/nova-settings.js`, `SPEC.md`, `TICKETS.md`).
- **Git commands run by me:** keine (rein statische Datei-Inspektion über die Read-Werkzeuge dieser Read-only-Review-Sitzung).
- **Checks evidenced by supplied raw output:**
  - Test-Agent-Nachlauf in `docs/reviews/AP4-Korbat-test-agent-report.md` §10.4:
    - `python3 -m unittest tests.unit.test_ap4_korbat_gui tests.unit.test_ap4_korbat_worktrees_sessions -v` → `Ran 41 tests in 14.887s, OK` (Exit 0)
    - `python3 -m unittest tests.unit.test_ap4_korbat_github -v` → `Ran 19 tests in 29.152s, OK` (Exit 0)
- **Checks reported only by the coding agent:**
  - `python3 -m unittest tests.unit.test_ap19_sessions_api tests.unit.test_f25_session_continue -v` → `Ran 33, OK`
  - `python3 -m unittest tests.unit.test_ap9_github -v` → `Ran 44, failures=1` (vorbestehender Baseline-Fehler `test_cli_clone_checks_out_the_requested_branch`, `NameError agent_note` am Basiscommit `212d97d`)
  - `python3 -m unittest tests.unit.test_ap06_github -v` → `Ran 54, failures=1` (vorbestehender `CliPushTest`-Baseline-Fehler)
  - `bash scripts/verify.sh quick` → Exit 0
  - `python3 scripts/check-import-manifest.py` → OK (67 Dateien)
  - `python3 scripts/check-syntax.py` → OK (211/8/3)
  - Runde-1-Volllauf-Nachweis: `verify.sh full` → `Ran 2244` (= 2178 Basis + 66 neue AP4-Fälle, alle grün) mit Per-Test-Abgleich gegen den umgebungsgleichen Basisvolllauf am Ausgangscommit `212d97d` (Ran 2178).
- **Checks not independently run:** Alle Build-, Test- und Git-Befehle (als Read-only-Reviewer nicht selbst ausgeführt); kein Playwright/Browser-Lauf und kein Lauf gegen die echte GitHub-API.
- **Important areas inspected:** `bin/vibe-web.py:670-678,1475-1586`, `bin/vibe:51,101-144,1169-1188,1949-2095`, `bin/web/nova-project.js:516-588,998-1020`, `bin/web/nova-settings.js:1-100`, `bin/vibe-run.sh:1624-1715`, `SPEC.md:324-372`, `docs/import-manifest.json:1179-1415`, `docs/features/AP4-Korbat.md`, `docs/reviews/AP4-Korbat-test-agent-report.md:443-518`, `tests/unit/test_ap4_korbat_gui.py:284-358`, `tests/unit/test_ap4_korbat_worktrees_sessions.py:758-859`, `tests/unit/test_ap4_korbat_github.py:566-631`.
- **Remaining risks:** Nur die bereits in Runde 1 und in `docs/features/AP4-Korbat.md` §5 ausgewiesenen Umgebungs- und Testgrenzen (JS-Oberflächen mangels Playwright über Quelltext-/Strukturassertions plus echte Backend-API-Tests geprüft; GitHub-REST über lokale Loopback-Fakes geprüft).

Verdict: PASS
