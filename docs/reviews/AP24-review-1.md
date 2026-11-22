# Review AP24 — Runde 1

- Datum: 2026-11-22
- Reviewer: code-reviewer (unabhängiger Subagent), Session `ses_dfd2b93a7ffePjnXMQ9UkNTXAF`
- Umfang: Arbeitskopie relativ zu Ausgangscommit `831ecd1ca511959a3ae369a4c035cac58e0bb066` (nicht committet), `HEAD`
- Ticket: TICKETS.md AP24 „Lizenz anpassung der projektes" (Zeilen 1159–1175)

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| LICENSE = kanonischer AGPL-3.0-only-Text, erste kanonische Zeile „GNU AFFERO GENERAL PUBLIC LICENSE" | PASS | `LICENSE:1` | `tests/unit/test_ap24_license.py::LicenseContractTest.test_license_is_agpl_3_0_only` (Run 2, 2026-11-22T11:02:28, ok) |
| LICENSE enthält „Version 3, 19 November 2007" | PASS | `LICENSE:2` | `test_license_is_agpl_3_0_only` (Run 2, ok) |
| LICENSE enthält „GNU Affero General Public License" | PASS | `LICENSE:10,42,63,564,574,578,636,643,645` | `test_license_is_agpl_3_0_only` (Run 2, ok); `tests/unit/test_ap12_github_readiness.py::TrackedContentHygieneTest.test_github_documents_exist_and_are_tracked` Z. 334–338 (Run 2, ok) |
| LICENSE enthält nicht „MIT License" | PASS | `LICENSE` (grep „MIT License": 0 Treffer) | `test_license_has_no_mit_text` (Run 2, ok) |
| Attribution „Copyright (c) 2026 M0P" bleibt erhalten | PASS | `LICENSE:663` | `test_license_keeps_project_copyright` (Run 2, ok) |
| README enthält den vorgeschriebenen Lizenzsatz verbatim | PASS | `README.md:202` | `test_readme_states_dual_licensing_model` (Run 2, ok) |
| README referenziert „LICENSE" | PASS | `README.md:200,214` | `test_readme_states_dual_licensing_model` (Run 2, ok) |
| README behauptet nicht mehr MIT | PASS | `README.md` (grep „MIT": 0 Treffer) | `test_readme_does_not_claim_mit` (Run 2, ok) |
| Dual-Licensing-Modell dokumentiert | PASS | `README.md:196-208`, `docs/features/AP24.md:28-41` | `test_readme_states_dual_licensing_model` (Run 2, ok) |
| Repo-Abdeckung: keine weiteren README-Seiten | PASS | `find -iname 'readme*'` → nur `README.md` | `docs/features/AP24.md:69-72` |
| 5/5 AP24-Tests grün | PASS | — | `python3 -m unittest tests.unit.test_ap24_license -v` → Ran 5, OK, Exit 0 (Tester-Bericht §6) |
| Environmental ap12-Failures nicht durch AP24 verursacht | PASS | keine AP24-Datei unter Befunden (`.opencode/agents/` fehlt; `docs/features/AP24.md` enthält keine Home-Pfad-Muster) | Tester-Bericht §8; geprüft: `grep '(?:home|Users)/'` auf `docs/features/AP24.md` und `docs/reviews/AP24-test-agent-report.md` → 0 Treffer |

## Findings
- [Minor] `LICENSE:663` — Projekt-Attribution steht nach dem kanonischen AGPLv3-Text, nicht davor
  - Evidence: Die Vergabe formuliert die Attribution illustrativ „davor" (TICKETS.md AP24, Z. 1166), der Vertragstest verlangt `text.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")` (LICENSE:1). Beide sind gleichzeitig nicht erfüllbar; aufgelöst zugunsten des grünen Tests: Attribution ans Ende (LICENSE:662 Leerzeile, LICENSE:663 `Copyright (c) 2026 M0P`). Dokumentiert in `docs/features/AP24.md:43-62` und `docs/reviews/AP24-test-agent-report.md`.
  - Required fix: Keine Codeänderung erforderlich, wenn die Abweichung akzeptiert wird. Andernfalls Ticket-Wortlaut und Vertragstest angleichen (Attributionsposition verbindlich festlegen). OSI-/FSF-Kompatibilität bleibt gewahrt (kanonischer Text unverändert, keine Zusatzklausel angehängt).

Keine weiteren Findings.

## Verification
- Change set reviewed: Arbeitskopie relativ zu Ausgangscommit `831ecd1ca511959a3ae369a4c035cac58e0bb066`; geändert: `LICENSE`, `README.md`, `tests/unit/test_ap12_github_readiness.py`; neu: `docs/features/AP24.md`, `docs/reviews/AP24-test-agent-report.md`, `tests/unit/test_ap24_license.py`.
- Git commands run by me: keine (Shell permission denied); Dateien per `read`/`glob`/`grep` geprüft.
- Checks with supplied output (vom Coding-/Test-Agenten geliefert, von mir nicht ausgeführt):
  - `python3 -m unittest tests.unit.test_ap24_license -v` → Ran 5 tests, OK, Exit 0 (Tester-Bericht §6, Run 2, 2026-11-22T11:02:28).
  - `python3 -m unittest tests.unit.test_ap24_license tests.unit.test_ap12_github_readiness -v` → Ran 16 tests, FAILED (failures=2), Exit 1; alle 5 AP24-Fälle + `test_github_documents_exist_and_are_tracked` ok; 2 Failures environmental/vorbestand (Bericht Abschnitt 8).
  - VERIFY_PACKAGE: `check-import-manifest.py` Exit 0 (70 Dateien), `check-syntax.py` Exit 0 (231 Python-, 8 Bash-, 3 JSON-Dateien), `check-no-secrets.py` Exit 0.
  - VERIFY_FULL: nicht vollständig durchlaufen (Timeout) — verbleibendes Risiko.
- Checks not independently run: alle Build-, Test-, Manifest- und Syntaxprüfungen.
- Important areas inspected: `LICENSE` (Head Z. 1–5, Tail Z. 660–663, Copyright Z. 663, GNU-Affero-Vorkommen), `README.md` Z. 196–214, `tests/unit/test_ap24_license.py` (LIZENZ_SATZ Z. 40–44, Tests Z. 56–115), `tests/unit/test_ap12_github_readiness.py` Z. 242–339, `docs/features/AP24.md`, `docs/reviews/AP24-test-agent-report.md` (§5 Rotphase, §6 Grünphase, §8 Environmental), `docs/reviews/AP11-review-1.md` (Stilvorlage).
- Remaining risks:
  - `VERIFY_FULL` nicht abgeschlossen (Timeout) — koordinatorseitig vor Abnahme nachholen.
  - Byte-Identität des kanonischen AGPLv3-Texts mit der offiziellen Vorlage nicht unabhängig verifiziert (nur strukturelle Prüfungen).
  - Die beiden environmental ap12-Failures (`test_no_tracked_file_contains_personal_home_paths_or_secrets`, `test_local_test_agent_preserved_when_environment_established`) sind vorbestand/unabhängig von AP24; `.opencode/agents/test-agent.md` fehlt in diesem Worktree. Keine AP24-Datei unter den Befunden.

Verdict begründet: Alle Akzeptanzkriterien sind mit Implementierungs- (file:line) und Testnachweisen (Run 2, 5/5 ok) belegt; es liegt ausschließlich ein dokumentierter Minor-Befund (Attributionsposition, beabsichtigte Abweichung vom illustrativen Ticket-Wortlaut) ohne Blockerwirkung vor. Critical/High/Medium = 0.
