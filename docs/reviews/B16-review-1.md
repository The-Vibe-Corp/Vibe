# B16 — Review Runde 1

**Paket:** FEEDBACK.md B16 „Fertiggestellte APs müssen für GitHub vorbereitet und als PR erstellt werden“
**Geprüfter Stand:** `d998a3e` (Test-Agent), `6b7209c` (Coding-Agent), Basis `0a197b4`
**Branch:** `vibe/vibe-B16-1795071980451527111-57043-225`
**Reviewer-Einschränkung:** Das `shell`-Werkzeug war gesperrt („Permission denied: shell“). Die Prüfung erfolgte filebasiert ohne Git-Diffs und ohne eigene Testläufe. Der Review-Inhalt stammt vom unabhängigen Review-Agenten und wurde wegen dessen read-only-Regel vom Orchestrierer wortgetreu persistiert.

## Summary
- Critical: 0
- High: 0
- Medium: 4
- Minor: 3
- Verdict: CHANGES REQUIRED

**Hinweis zum Prüfumfang:** Change-Set-Diff und Tests konnten nicht unabhängig abgerufen bzw. ausgeführt werden. Wo nur Agentenangaben vorliegen, ist das in der Tabelle als NOT VERIFIED markiert.

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| (a) Branch-Namen `feature/...` statt `vibe/...`, über `PACKAGE_BRANCH_PATTERN` konfigurierbar | PASS | `bin/vibe_packages.py:424-426`, `:503-547`, `:1447-1459`; `bin/vibe-run.sh:449-467` | `tests/unit/test_b16_branch_name.py` (20 Fälle), `tests/unit/test_b16_runner_wiring.py::test_successful_run_pushes_feature_branch_and_opens_the_pr`; Ausgabe „20 Tests OK“ nur als Agentenangabe |
| (b) `github-complete` als harte Schranke: kein `[x]`, kein lokaler Merge, Status blocked mit Begründung | PASS | `bin/vibe-run.sh:1159-1175`; `bin/vibe_github.py:1103-1161` | `tests/unit/test_b16_runner_wiring.py::BlockedClosureTest` (`:150-209`); Ausgabe „6 Tests OK“ nur als Agentenangabe |
| (c) Bei divergiertem `dev` vor Abschluss abbrechen und informieren | PASS | `bin/vibe_github.py:1038-1100`, Aufruf `:1130-1132` | `tests/unit/test_b16_github_closure.py` (`:289-399`), `tests/unit/test_b16_runner_wiring.py::DivergenceTest` (`:216-249`); „18 Tests OK“ nur als Agentenangabe |
| (d) Abschlussbericht enthält Branch, PR-URL und Commit | FAIL | `bin/vibe-run.sh:1001-1008`, `:1174-1175` | Branch/PR geprüft, **Commit-Anteil nicht getestet**: `test_b16_runner_wiring.py:134-136,270-273`; `test_worknotes_sync.py:658` prüft nur den FEEDBACK-Nachweis |
| (e) Tests für Erfolgs-/Fehlerpfade plus Doku in `docs/features/` und AGENTS.md | FAIL | `docs/features/B16.md` vorhanden; GENERAL_RULES in `bin/vibe:101-140` und Templates | `docs/features/AP9.md:99-106` beschreibt weiterhin die überholte Hinweis-Semantik; Testtabelle `B16.md:137,150-162` veraltet |

## Findings
- [Medium] `docs/features/AP9.md:99-106` — AP9-Doku beschreibt weiterhin die abgelöste Hinweis-Semantik für den Abschluss
  - Evidence: „Ein Fehlschlag … ist ein HINWEIS; der lokale Merge läuft weiter“ widerspricht `bin/vibe-run.sh:1159-1175` und `bin/vibe_github.py:1103-1161`.
  - Required fix: AP9-Abschnitt „Läufer-Automatik“ auf B16-Semantik umstellen und auf `docs/features/B16.md` verweisen.
- [Medium] `tests/unit/test_runner_package_gates.py:195-196` und `tests/unit/test_worknotes_sync.py:674-678` — Cleanup-Assertions prüfen `vibe/*`, das nach B16 nicht mehr erzeugt wird
  - Evidence: Default ist `feature/{owner}/{id}` (`bin/vibe_packages.py:425`); die Assertion ist immer erfüllt.
  - Required fix: Durch den Test-Agenten auf das tatsächliche Branch-Muster umstellen lassen.
- [Medium] `tests/unit/test_b16_runner_wiring.py:132-143,269-291` — Kein Test deckt den Commit-Anteil der Berichtszeile ab (Anforderung d)
  - Evidence: Nur Branch und Merge-Request werden geprüft; `CLOSED_COMMIT` aus `bin/vibe-run.sh:1004-1006` bleibt ungetestet.
  - Required fix: Commit-Angabe gegen den tatsächlichen Projekt-HEAD prüfen (Erfolgs- und Skip-Fall).
- [Medium] `docs/features/B16.md:137,150-162` — Paketdokumentation widerspricht dem Testbericht
  - Evidence: „1 Failure“/„Offener Befund“, obwohl `docs/reviews/B16-test-agent-report.md:291-327` die Fixture-Korrektur und den grünen Lauf belegt.
  - Required fix: Testtabelle und „Offener Befund“ auf den Stand nach der Fixture-Korrektur bringen.
- [Minor] `bin/vibe_packages.py:33-47` i. V. m. `bin/vibe-run.sh:1162-1171` — Fehlendes `vibe_github.py` erzeugt BLOCKIERT-Zeile ohne Ursache
  - Evidence: `SystemExit`-Meldung nur auf stderr; `GH_COMPLETE_OUT` leer; Zeile endet mit leerer Ursache.
  - Required fix: Feste Ersatzursache bei leerer Ausgabe nennen.
- [Minor] `AGENTS.md:9-17` — Root-`AGENTS.md` enthält die neuen B16-Regeln nicht
  - Evidence: Der verwaltete Block entspricht der bisherigen Fassung; neue Regeln nur in `bin/vibe` und Templates.
  - Required fix: Klären, ob der Root-Block bewusst nur Laufzeitstand ist; andernfalls synchronisieren.
- [Minor] `docs/features/B16.md:132-148` — Testtabelle ohne Datum/Umgebung je Lauf
  - Evidence: Ergebnisse ohne Zeitstempel; nicht erkennbar, welche Nachweise nach dem letzten Code-Stand entstanden.
  - Required fix: Laufzeiten und maßgebliche Läufe kennzeichnen.

## Verification
- Change set reviewed: `0a197b4..working tree` — Diff nicht abrufbar; Dateiinhalte im Worktree geprüft.
- Git commands run by me: keine — `shell` gesperrt.
- Checks with supplied output: nur `docs/reviews/B16-test-agent-report.md:315-327` (3 Tests OK, 6 Tests OK); alle übrigen Ergebnisse nur Agentenangaben.
- Checks not independently run: alle Build-, Syntax-, Manifest-, Secret- und Testprüfungen.
- Important areas inspected: harte GitHub-Schranke, `integration_state`/`complete_package`/`push`, `package_branch_name`, Berichtsformat, Worktree-Cleanup, GENERAL_RULES, B16-/AP9-Doku.
- Remaining risks: Testgrün nicht unabhängig belegt; Manifest-Hashes nicht verifizierbar; vorbestehende rote Suiten nicht nachgeprüft.

**Verdict: CHANGES REQUIRED**
