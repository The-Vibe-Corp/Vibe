# AP9 — Review Runde 2 (code-reviewer)

Datum: 2026-11-11
Reviewer: code-reviewer (unabhängig, Subagent session ses_e3743e1fbffeJXgh1xingEZTub)
Gegenstand: Arbeitspaket AP9 „Bereit für github teil 3", Ausgangscommit `4b51ae4`, Implementierungscommit `7680675`, Behebungscommit `b6ad8df`, Arbeitsbaum `vibe/vibe-AP9-1794355960880323502-2529435-4459`
Antwort des Reviewers unverändert aus der Review-Antwort übernommen (siehe Hinweis am Ende).

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

## Acceptance criteria

Die fachlichen Akzeptanzkriterien wurden in Runde 1 bereits mit Implementierungs- und Testnachweisen je PASS bewertet (`docs/reviews/AP9-review-1.md`, Tabelle). Der Behebungscommit `b6ad8df` ändert keine Fachfunktion — nur Docstring/Kommentar (`bin/vibe_github.py`), UI-Hinweistext (`bin/web/app.js`) und Dokumentation/Tests. Die Kernkriterien bleiben daher auf Runde-1-Basis gültig, soweit die Stellen unverändert sind (verifiziert über den Gesamtstand `4b51ae4..b6ad8df`):

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Token je Projekt gespeichert | PASS | `bin/vibe_github.py` (unchanged in b6ad8df, Runde-1-Stand) | `tests/unit/test_ap9_github.py:ProjectTokenStoreTest` (44/44 OK, geliefert) |
| Token verschlüsselt | PASS | `bin/vibe_github.py` (unchanged in b6ad8df) | `test_stored_file_is_encrypted_and_never_carries_the_plaintext`, `test_tampered_ciphertext_returns_empty_string` (geliefert) |
| Branch auschecken / Push-Ziel | PASS | `bin/vibe_github.py` (unchanged), `bin/web/app.js:703-705` (Knöpfe unverändert) | `CheckoutBranchTest`, `PushTargetTest`; Browser 5/5 (geliefert) |
| Nach jedem AP Merge-Request (sofern konfiguriert) | PASS | `bin/vibe-run.sh:677-684`, `bin/vibe_github.py:962` (`enabled`-Schranke), `945-987` (`complete_package`) | **NEU:** `tests/unit/test_ap9_runner_wiring.py:CompleteWiringTest.test_complete_is_not_called_when_the_gate_is_red` (3/3 OK, geliefert); Subkommandos `test_ap9_runner_github.py` 17/17 |
| Vor jedem AP Haupt-Branch pullen | PASS | `bin/vibe-run.sh:597-604` (nach `select_item`, vor `PACKAGE_BASE`), `bin/vibe_github.py:927` | **NEU:** `test_ap9_runner_wiring.py:PullWiringTest` (beide Fälle); `PullIntegrationTest` (geliefert) |
| Feature-Branch je AP, nur darin arbeiten | PASS (dokumentiert, AP5-Bestand) | `bin/vibe-run.sh:606` (`create_worktree`); `docs/features/AP9.md:90-92` | Doku-Nachweis |
| UI-Feedback Verbindungen | PASS | `bin/vibe-web.py`/`bin/web/app.js` (unchanged in b6ad8df) | Browser `test_connection_test_button_shows_an_ok_result_line` u. a. (geliefert) |
| B7-Rückwärtskompatibilität | PASS | Legacy-Funktionen unverändert (b6ad8df berührt sie nicht) | `test_b7_github_auth.py` (geliefert, 31/31) |

## Behandlung der Runde-1-Befunde (eigene Prüfung am Diff `7680675..b6ad8df`)

1. **[Medium, Runde 1] „kein automatischer Push oder Merge“ — behoben.** `bin/web/app.js:702` nennt jetzt Läufer-Automatik (Pull vor jedem Paket, Push + Merge-Request nach Abschluss, Merge manuell); `bin/vibe_github.py:4-14` (Docstring) beschreibt dieselbe Auslegung. Ich habe die Aussagen gegen den Code geprüft: `pull_integration`/`complete_package` sind tatsächlich an `config["enabled"]` (`GITHUB_ENABLED`) gekoppelt (`bin/vibe_github.py:927,962`) — die neuen Texte sind zutreffend. Kein Test behauptet den alten Text (`grep` über `tests/` ohne Treffer auf die alte Formulierung), die Browser-Suiten bleiben dadurch unberührt.
2. **[Minor] Doku-Befehl — behoben.** `docs/features/AP9.md:63` nennt `vibe clone --branch <b>`; implementiert unter `bin/vibe:23` (Hilfetext) und `_parse_clone_cli` (`bin/vibe:2594-2602`).
3. **[Minor] SPEC-Konflikt — behoben.** `docs/features/AP9.md:113-122` erläutert die Auslegung („Grenzen“, Abschnitt „SPEC-Konflikt, erläutert“) gemäß AGENTS-Auftrag „Widerspruch zwischen Ticket und SPEC: Konflikt erläutern“.
4. **[Minor] Läufer-Verkabelung ungetestet — behoben.** `tests/unit/test_ap9_runner_wiring.py` (neu, 303 Zeilen, 3 Tests) läuft den echten `vibe-run.sh` in einer Fake-Toolchain. Ich habe die Testerwartungen gegen den Code geprüft: Pull-Position nach `select_item` und vor `PACKAGE_BASE`/Kopf (`bin/vibe-run.sh:596-605`, HINWEIS-Text Zeile 601), `github-complete` erst nach grüner Schranke und vor `merge_package` (`bin/vibe-run.sh:656-685`, HINWEIS-Text Zeile 683, Schranken-Text „Abschlussschranke für $ID nicht erfüllt“ Zeile 657) — Test und Implementierung decken sich exakt. Der Test benutzt nur unveränderte Harness-Bausteine (`tests/unit/runner_support.py`: `FAKE_MODE="no-artifacts"` Zeile 216, `impl-`-Datei Zeile 261) und wurde selbst nicht abgeschwächt; `runner_support.py` ist im Änderungssatz nicht enthalten.
5. **[Minor] scrypt je Aufruf — behoben.** `docs/features/AP9.md:133-138` dokumentiert den bewusst akzeptierten Kompromiss mit Verweis auf die Projekt-Caching-Regeln.
6. **[Minor] Kommentar — behoben.** `bin/vibe_github.py:971-973` benennt korrekt, dass `set_head_default` den Remote abfragt.

## Findings

- [Minor] Trilium-Notiz `RZaerCNe9ngJ` — Notizstand hinter dem Behebungsstand
  - Evidence: Ich habe die Notiz unabhängig über Trilium-MCP gelesen (Titel „AP9 Bereit für GitHub Teil 3 …", Inhalt passend zur Runde-1-Doku). Die Runde-2-Ergänzungen fehlen dort: SPEC-Konflikt-Auslegung und scrypt-Kompromiss stehen nicht in der Notiz (Suche nach „SPEC" ohne Treffer), die neue Verkabelungsprüfung `test_ap9_runner_wiring.py` ist in der Prüfungsliste nicht genannt. Keine fachliche Auswirkung; die Notiz muss vor dem Abschlussaktualisieren werden.
  - Required fix: Beim Abschlussaktualisieren (vor Abhaken in TICKETS.md) die Trilium-Notiz um die Runde-2-Punkte ergänzen (SPEC-Auslegung, scrypt-Kompromiss, Runner-Verkabelungstest 3/3) und den Schreibvorgang verifizieren.

## Verification
- Change set reviewed: `4b51ae4..b6ad8df` (Gesamtstand, HEAD = b6ad8df, sauberer Arbeitsbaum) sowie gezielt `git diff 7680675..b6ad8df` (Behebung); alle 7 geänderten/neuen Dateien des Behebungscommits gelesen, `tests/unit/test_ap9_runner_wiring.py` vollständig, `docs/features/AP9.md` vollständig.
- Git commands run by me: `git status --short`, `git log --oneline -8`, `git diff --stat 7680675..b6ad8df`, `git diff --stat 4b51ae4..b6ad8df`, `git diff 7680675..b6ad8df -- bin/vibe_github.py bin/web/app.js`, `git diff 4b51ae4..b6ad8df -- docs/import-manifest.json docs/baseline.md`, `git show --stat b6ad8df`. Plus werkzeugbasierte greps/reads.
- Checks with supplied output (vom Coding-/Test-Agenten geliefert, von mir nicht wiederholt): `test_ap9_runner_wiring.py` 3/3 OK; kombinierter Lauf 182/182 OK; `verify.sh quick` OK (Manifest 57 Dateien — die Zahl 57 habe ich unabhängig durch Zählen der Manifest-Einträge bestätigt); `verify.sh full` 1460 Tests mit 3 dokumentierten Baseline-Fehlschlägen an `4b51ae4`, kein neuer Fehlschlag laut Abgleich; `check-import-manifest.py` OK; `test_baseline_inventory` 8/8 OK.
- Checks not independently run: alle Unit-, Browser-, Verify- und Manifest-Skriptläufe (meine Berechtigung ist auf read-only Git beschränkt); ich habe nichts ausgeführt. Trilium habe ich unabhängig per MCP gelesen (siehe oben).
- Important areas inspected: Behebungs-Diff komplett; Läufer-Verkabelung `bin/vibe-run.sh:596-705` gegen die Testerwartungen; `tests/unit/runner_support.py` (Harness-Verträglichkeit, unverändert); `.vibe/project.env` (`TESTER=test-agent`); TICKETS.md (AP9 noch offen — korrekt, Abhaken erst nach finalem PASS mit Nachweisen); Trilium-Notiz.
- Remaining risks: Die Testergebnisse (3/3, 182/182, verify quick/full) sind nur Auslieferungszeuge des Coding-/Test-Agenten, nicht mein Befund — insbesondere die Behauptung „keine neuen Fehlschläge gegenüber 4b51ae4" basiert auf dem gelieferten Abgleich. Die Autorenschaft der neuen Testdatei (Test-Agent) kann ich nicht unabhängig belegen; sie ist plausibel (TESTER-Konfiguration vorhanden, Harness-Konventionen des Test-Agenten verwendet, Coding-Seite hat laut Änderungssatz keine Testdatei angelegt). Kein echtes GitHub/Netz wurde je geprüft (per Doku beabsichtigt).

## Urteil

Verdict: PASS

Befundsliste Runde 2: Critical 0 · High 0 · Medium 0 · Minor 1 (Trilium-Notiz aktualisieren vor Abschluss) · Info 0. Alle sechs Runde-1-Befunde sind vollständig und korrekt behandelt; der Behebungscommit enthält ausschließlich das Arbeitspaket samt Nachweisen (7 Dateien, keine Fremdänderungen, keine veränderte Prüfwerkzeuge, keine abgeschwächten Tests).

---

Hinweis: Diese Datei ist die wortgleiche Übernahme der Review-Antwort des
unabhängigen Reviewers (code-reviewer, Subagent). Formatvorlage:
docs/reviews/AP8-review-2.md.
