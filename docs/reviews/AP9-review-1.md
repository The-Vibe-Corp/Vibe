# AP9 — Review Runde 1 (code-reviewer)

Datum: 2026-11-11
Reviewer: code-reviewer (unabhängig, Subagent session ses_e375766a2ffeIkA5R6kDa9Hj5Q)
Gegenstand: Arbeitspaket AP9 „Bereit für github teil 3", Ausgangscommit `4b51ae4`, Implementierungscommit `7680675`, Arbeitsbaum `vibe/vibe-AP9-1794355960880323502-2529435-4459`
Antwort des Reviewers unverändert aus der Review-Antwort übernommen (siehe Hinweis am Ende).

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 5
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| GitHub-Token je Projekt gespeichert | PASS | `bin/vibe_github.py:121-131,230-257` (`_project_digest`, `_project_token_path`, `save_project_token`) | `tests/unit/test_ap9_github.py:ProjectTokenStoreTest` (44/44 OK, geliefert; nicht unabhängig wiederholt) |
| Token verschlüsselt gespeichert | PASS | `bin/vibe_github.py:165-227` (scrypt + HMAC-Strom + Encrypt-then-MAC, Defekt → Leerwert) | `test_ap9_github.py:test_stored_file_is_encrypted_and_never_carries_the_plaintext`, `test_tampered_ciphertext_returns_empty_string` (geliefert) |
| Mehr Kontrolle: Branch auschecken | PASS | `bin/vibe_github.py:796-830` (`checkout_branch`), `bin/vibe` (`cmd_github` „checkout“), `bin/web/app.js:689-694` (Wechseln-Knopf je Branch-Zeile) | `test_ap9_github.py:CheckoutBranchTest`; Browser `test_ap9_github_ui.py:test_branch_rows_offer_wechseln_and_push_and_they_work` (5/5 OK, geliefert) |
| Mehr Kontrolle: Push-Ziel | PASS | `bin/vibe_github.py:833-854` (`push` mit Refspec `<branch>:<target>`), CLI/Web übernommen | `test_ap9_github.py:PushTargetTest` (geliefert) |
| Feature-Branch je AP, nur darin arbeiten | PASS (dokumentiert, durch AP5 bereits gegeben) | `bin/vibe-run.sh:212-227` (`create_worktree`, unverändert); `docs/features/AP9.md:91-93` | Doku-Nachweis; kein neuer Test nötig (Bestand) |
| Nach jedem AP automatischer Merge-Request (sofern konfiguriert) | PASS | `bin/vibe-run.sh:681-684` (github-complete nach grüner Schranke), `bin/vibe_github.py:945-987` (`complete_package`), `bin/vibe_packages.py:1018-1032,1120-1134` | `tests/unit/test_ap9_runner_github.py:CompletePackageTest`, `SubcommandExitCodesTest` (17/17 OK, geliefert); Läufer-Verkabelung selbst ungetestet (siehe Findings) |
| Vor jedem AP Haupt-Branch pullen | PASS | `bin/vibe-run.sh:600-602` (github-pull nach select), `bin/vibe_github.py:908-942` (`pull_integration`, fetch + ff-only mit explizitem Refspec) | `test_ap9_runner_github.py:PullIntegrationTest` (geliefert) |
| UI-Feedback, ob Verbindungen funktionieren | PASS | `bin/vibe_github.py:857-905` (`connection`), `bin/vibe-web.py:917-921` (Aktion `connection`), `bin/web/app.js:662-670,714-716` (Knopf + Ergebniszeile) | `test_ap9_github.py:ConnectionTest`; Browser `test_connection_test_button_shows_an_ok_result_line`, `test_connection_test_shows_a_distinct_error_marking` (geliefert) |
| B7-Rückwärtskompatibilität | PASS | Legacy `save_token/read_stored_token/token_state_path` erhalten (`bin/vibe_github.py:300-353`); Präzedenz env > projekt > legacy (`token_status` 356-367) | `tests/unit/test_b7_github_auth.py:TokenStoreTest` unverändert; Migration der Routentests durch Test-Agenten ohne Abschwächung (31/31 OK, geliefert; `credentials_scope_texts` prüft argv+ENV, damit bleibt der URL-Scoping-Vertrag geprüft) |

## Findings
- [Medium] `bin/web/app.js:698` (und `bin/vibe_github.py:4-6`) — Falsche Verhaltensaussage „kein automatischer Push oder Merge“
  - Evidence: Die Karte sagt wörtlich „Updates und Branches bleiben bewusste Aktionen (kein automatischer Push oder Merge)“, und der Modul-Docstring behauptet weiterhin, GitHub-Funktionen würden „nie automatisch etwas“ ändern und Pushes/Merge-Requests seien „bewusste Nutzerentscheidungen“. Seit AP9 pusht der Läufer mit derselben Konfiguration (`GITHUB_ENABLED=1`) nach jedem abgeschlossenen Paket automatisch den Branch und stellt einen Merge-Request (`bin/vibe-run.sh:681-684`, `bin/vibe_github.py:945-987`). Nutzer, die der Oberfläche vertrauen, werden über eine sicherheitsrelevante Automatik (automatische Veröffentlichung von Paket-Branches) falsch informiert. (Das Mergen selbst bleibt manuell — das ist korrekt.)
  - Required fix: UI-Text und Modul-Docstring auf den AP9-Stand korrigieren: Mit `GITHUB_ENABLED` zieht der Läufer vor jedem Paket den Haupt-Branch und pusht nach jedem abgeschlossenen Paket automatisch den Paket-Branch samt Merge-Request; die Knöpfe in der Karte bleiben bewusste Nutzeraktionen, das Zusammenführen bleibt manuell.
- [Minor] `docs/features/AP9.md:64` — Nicht existierender CLI-Befehl dokumentiert
  - Evidence: Doku nennt `vibe checkout <url> --branch <b>`; implementiert ist `vibe clone <url> [name] --branch <b>` (Hilfetext `bin/vibe:23`, `_parse_clone_cli` in `bin/vibe`).
  - Required fix: Doku-Zeile auf den tatsächlichen Befehl `vibe clone … --branch` korrigieren.
- [Minor] `docs/features/AP9.md` (Abschnitt „Grenzen“) — SPEC-Konflikt nicht erläutert
  - Evidence: SPEC.md:320 stellt „Automatische Veröffentlichung, Push, Merge oder Release ohne Freigabe“ außerhalb des Umfangs; AP9/TICKETS.md verlangt automatisch Push + Merge-Request nach jedem AP. Die Umsetzung entschärft dies (nur bei ausdrücklicher `GITHUB_ENABLED`-Konfiguration, Merge bleibt manuell), aber der Widerspruch ist laut AGENTS.md („Widerspruch zwischen Ticket und SPEC: Konflikt erläutern“) nirgends dokumentiert.
  - Required fix: Entscheidung in `docs/features/AP9.md` (oder Entscheidungsnotiz) erläutern: die `GITHUB_ENABLED`-Konfiguration gilt als stehende Freigabe für Push/Request, das Zusammenführen bleibt manuell.
- [Minor] `bin/vibe-run.sh:600-602,681-684` — Läufer-Verkabelung ohne Testabdeckung
  - Evidence: Getestet sind `pull_integration`/`complete_package` und die Subkommandos; dass `vibe-run.sh` die beiden Aufrufe an den richtigen Positionen (nach `select_item` bzw. vor `merge_package`) mit HINWEIS-Verhalten ausführt, prüft kein Test. Eine Regression in der Verkabelung (falsche Position, vertauschte Exit-Behandlung) würde unbemerkt bleiben.
  - Required fix: either eine Runner-Ebene-Prüfung beim Test-Agenten anfragen oder die Position/Begründung in der Doku als manuell geprüft markieren.
- [Minor] `bin/vibe_github.py:503` — scrypt-Ableitung bei jedem Git-Aufruf wiederholt
  - Evidence: `git()` löst bei jedem Aufruf den Projekt-Token neu auf (Dateilesen + scrypt n=2¹⁴). `status()`/`branches()` führen viele Git-Aufrufe je Dashboard-Ladung aus; bei vielen Branches summiert sich das spürbar. Kein funktionaler Fehler; ein Cache wäre laut Projektregeln nur mit benannter Invalidierung zulässig.
  - Required fix: optional den Token einmal pro Aufrufkette auflösen oder wiederholtes Ableiten in der Doku als bewusst akzeptierten Kompromiss nennen.
- [Minor] `bin/vibe_github.py:967-968` — ungenauer Kommentar
  - Evidence: „(kein weiterer Fernaufruf)“ über `set_head_default` — `git remote set-head origin --auto` kontaktiert sehr wohl den Remote.
  - Required fix: Kommentar präzisieren (z. B. „begrenzter Nachversuch, fragt origin/HEAD automatisch ab“).

## Verification
- Change set reviewed: `4b51ae4..7680675` (Implementierungscommit, HEAD), plus uncommittete Arbeitsbaumelemente `docs/baseline.md` (M) und `docs/features/AP9.md` (neu, untracked). Alle 12 geänderten und 3 neuen Dateien vollständig gelesen.
- Git commands run by me: `git status --short`, `git log --oneline -8`, `git diff --stat 4b51ae4..7680675`, `git diff 4b51ae4..7680675 -- <jeweils bin/vibe, bin/vibe_github.py, bin/vibe_packages.py, bin/vibe-web.py, bin/vibe-run.sh, bin/web/app.js, docs/import-manifest.json, tests/unit/test_b7_github_auth.py, tests/browser/test_b7_github_auth_ui.py>`, `git diff 4b51ae4 -- docs/baseline.md`, `git diff 4b51ae4..7680675 --stat -- scripts/ tests/support/`.
- Checks with supplied output (vom Coding-/Test-Agenten geliefert, von mir nicht wiederholt): 44/44, 17/17, 31/31, 33/33 Unit; 5/5 und 7/7 Browser; `verify.sh quick` OK; `verify.sh full` 1460 Tests mit 3 Baseline-Fehlschlägen, die laut Lieferung identisch an 4b51ae4 auftreten; `check-import-manifest.py` OK; `test_baseline_inventory` 8/8 OK. Trilium-Dokumentation habe ich unabhängig verifiziert: Notiz `RZaerCNe9ngJ` („AP9 Bereit für GitHub Teil 3 …“, Labels project=vibe, arbeitspaket=AP9, Branch-Label) existiert mit passendem Inhalt.
- Checks not independently run: alle Build-/Test-/Verify-Läufe (meine Berechtigung beschränkt sich auf read-only Git; ich habe nichts ausgeführt).
- Important areas inspected: `bin/vibe_github.py` (vollständig, inkl. Diff gegen AP8), `bin/vibe` (GitHub-CLI/Clone-Diff), `bin/vibe_packages.py` (Subkommandos), `bin/vibe-run.sh` (Läuferpositionen), `bin/vibe-web.py` (/api/github), `bin/web/app.js` (GitHub-Karte), alle drei AP9-Testdateien und die B7-Migration, `docs/features/AP9.md`, Manifest-Diff, AGENTS.md/SPEC.md/TICKETS.md.
- Remaining risks: Die gelieferten Testergebnisse und der Baseline-Abgleich der drei Fehlschläge sind nur Auslieferungszeuge, nicht mein Befund. `docs/features/AP9.md`, `docs/baseline.md` und später `docs/reviews/AP9-review-*.md` sowie der TICKETS.md-Eintrag (Commit/Test/Review/Doku) sind noch nicht committet und müssen nach der Behebung in den Abschlusscommit (AP9-Nachweise). Kein echtes Netz/ein echtes GitHub wurde je geprüft (per Doku beabsichtigt).

Verdict: CHANGES REQUIRED

---

Hinweis: Diese Datei ist die wortgleiche Übernahme der Review-Antwort des
unabhängigen Reviewers (code-reviewer, Subagent). Formatvorlage:
docs/reviews/AP8-review-1.md.
