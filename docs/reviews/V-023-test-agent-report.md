# V-023 — Bericht des unabhängigen Test-Agenten

Datum: 2026-11-08
Arbeitspaket: V-023 „Abschlussschranke erkennt bereits gemergte Pakete“
Testdatei: `tests/unit/test_gate_already_integrated.py`
Testbefehl:

```
python3 -m unittest discover -s tests/unit -p 'test_gate_already_integrated.py' -v
```

Der Test-Agent hat die Fälle aus Arbeitspaket, `SPEC.md` und `AGENTS.md`
abgeleitet, vor der Implementierung geschrieben und ausgeführt. Die
Produktionsdateien hat er nicht geändert; bestehende Tests blieben unberührt.

## Testfälle

| Testname | Vorbedingung | Aktion | Erwartetes Ergebnis | AK |
|---|---|---|---|---|
| `test_integrated_package_without_new_commits_passes` | Paketcommit `F1: Umsetzung`, Feature-Doku und `Verdict: PASS` liegen in `base`; getickte `FEEDBACK.md` ignoriert/uncommitted; kein Commit seit `base` | `gate_errors(project, "F1", base)` | `[]` | A1, A6 |
| `test_integrated_package_proof_equal_to_base_passes` | Nachweis-Commit ist selbst `base` (Fast-Forward), Doku und Review im selben Commit, Notiz `[x]` | Gate prüfen | `[]` | A1 |
| `test_integrated_package_listed_in_tickets_passes` | Wie A1, Nachweis steht in `TICKETS.md` | Gate prüfen | `[]` | A1 |
| `test_uncommitted_work_notes_do_not_block_the_integrated_package` | `FEEDBACK.md` ist per `.gitignore` ausgenommen, `git status --porcelain` leer | Ignore-/Statusprüfung und Gate | Notiz ignoriert, `[]` | A6, A1 |
| `test_integrated_proof_commit_without_package_prefix_still_blocks` | Nachweis-Commit Vorfahre von `base`, Betreffzeile ohne `F1:` | Gate prüfen | Befunde „Kein Commit seit dem Integrationsstand.“ und „Präfix“ bleiben | A2 |
| `test_proof_commit_on_another_branch_still_blocks` | Nachweis-Commit liegt auf anderem Zweig, nicht Vorfahre von `base` | Gate prüfen | blockierend, Befund enthält „Nachweis“ | A3 |
| `test_unknown_proof_commit_still_blocks` | Nachweis nennt nicht existierenden Commit `abcdef1` | Gate prüfen | blockierend, Befund enthält „Nachweis“ | A3 |
| `test_new_package_with_new_commits_passes` | Neuer Präfix-Commit, Doku, PASS-Review und vollständiger Nachweis seit `base` | Gate prüfen | `[]` | A4 |
| `test_new_package_without_prefix_still_blocks` | Neue Commits ohne `F1:` | Gate prüfen | Befund „Präfix“ | A4 |
| `test_proof_commit_outside_the_package_range_still_blocks` | Nachweis zeigt auf Commit vor `base` | Gate prüfen | Befund „Nachweis“ | A4 |
| `test_new_package_without_feature_documentation_still_blocks` | Neue Commits, `docs/features/F1.md` fehlt | Gate prüfen | Befund „docs/features“ | A4 |
| `test_new_package_without_review_still_blocks` | Kein Review vorhanden | Gate prüfen | Befund „Review“ | A4 |
| `test_new_package_with_review_without_pass_still_blocks` | Review mit `CHANGES REQUIRED` | Gate prüfen | Befund „PASS“ | A4 |
| `test_new_package_with_newer_review_without_pass_still_blocks` | Älteres PASS, neueres Review ohne PASS | Gate prüfen | Befund „PASS“ | A4 |
| `test_new_package_with_unchecked_ticket_still_blocks` | Ticket `[ ]` | Gate prüfen | Befund „nicht abgehakt“ | A4 |
| `test_new_package_with_incomplete_proof_still_blocks` | `Commit:` vorhanden, `Test:`/`Datei:` fehlt | Gate prüfen | Befund „Nachweis“ | A4 |
| `test_unrelated_new_commit_does_not_activate_the_shortcut` | Paket in `base`, danach fremder Commit ohne Präfix; Nachweis zeigt auf alten Paketcommit | Gate prüfen | Befund „Präfix“, kein Durchlassen | A1/A4 |
| `test_new_package_commit_does_not_accept_the_old_proof_commit` | Paket in `base`, neuer Präfix-Commit, Nachweis zeigt auf alten Commit | Gate prüfen | Befund „Nachweis“ | A4 |
| `test_integrated_package_with_unchecked_ticket_still_blocks` | Integriert, Ticket `[ ]` | Gate prüfen | Befund „nicht abgehakt“ | A5 |
| `test_integrated_package_without_proof_still_blocks` | Integriert, kein `Commit:`/`Test:` | Gate prüfen | Befund „Nachweis“ | A5 |
| `test_integrated_package_with_incomplete_proof_still_blocks` | Integriert, `Commit:` ohne `Test:`/`Datei:` | Gate prüfen | Befund „Nachweis“ | A5 |
| `test_integrated_package_without_feature_documentation_still_blocks` | Integriert, `docs/features/F1.md` fehlt | Gate prüfen | Befund „docs/features“ | A5 |
| `test_integrated_package_without_review_still_blocks` | Integriert, kein Review | Gate prüfen | Befund „Review“ | A5 |
| `test_integrated_package_with_review_without_pass_still_blocks` | Integriert, Review ohne PASS | Gate prüfen | Befund „PASS“ | A5 |

## Rotphase (Ausgangsstand `ab599cd`, ohne Implementierung)

Zur Behebung des Reviewbefunds wurde der Lauf nachträglich durch den
Koordinator in einem separaten Arbeitsbaum auf `ab599cd` reproduziert, in den
nur die neue Testdatei kopiert wurde:

```
git worktree add --detach /tmp/opencode/v023-baseline ab599cd
cp tests/unit/test_gate_already_integrated.py /tmp/opencode/v023-baseline/tests/unit/
cd /tmp/opencode/v023-baseline
python3 -m unittest discover -s tests/unit -p 'test_gate_already_integrated.py' -v
```

Ergebnis: `Ran 24 tests`, `FAILED (failures=4)`, Exit-Code 1.

Fehlgeschlagen sind ausschließlich die vier neuen Positivfälle:

- `AlreadyIntegratedPassTest.test_integrated_package_without_new_commits_passes`
- `AlreadyIntegratedPassTest.test_integrated_package_proof_equal_to_base_passes`
- `AlreadyIntegratedPassTest.test_integrated_package_listed_in_tickets_passes`
- `AlreadyIntegratedPassTest.test_uncommitted_work_notes_do_not_block_the_integrated_package`

Alle vier scheiterten mit den bisherigen drei Commit-Befunden („Kein Commit
seit dem Integrationsstand.“, „Commit mit Präfix 'F1:' fehlt.“,
„Nachweis-Commit … gehört nicht zu diesem Paketbranch.“). Die übrigen 20
Fälle waren bereits grün; die Rotphase ist damit ursächlich auf das fehlende
neue Verhalten zurückzuführen und nicht auf einen Testsetup-Fehler.

## Grünphase (Branch `feature/gate-bereits-integriert`)

- Neue Testdatei: `Ran 24 tests`, `OK`, Exit 0.
- Bestehende Gate-/Sync-Tests:
  `python3 -m unittest tests.unit.test_package_gates tests.unit.test_runner_package_gates tests.unit.test_worknotes_sync`
  → `Ran 64 tests`, `OK`, Exit 0.

## Verbleibende Lücken

- Geprüft wird `gate_errors` direkt, nicht der CLI-Wrapper `command_gate`.
- Nachweise werden als Kurz-Hashes getestet; Lang-Hashes sind über
  `COMMIT_PATTERN` zulässig, aber nicht separat abgedeckt.
- Merge-Commits als Basis und echte `git worktree`-Kopien sind nicht Teil
  dieser Testdatei; die bestehenden Arbeitskopie-Tests bleiben unberührt.
- Keine Modellaufrufe, keine externen Dienste, keine produktiven
  Konfigurationen verwendet.
