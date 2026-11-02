# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 3 (übernommen aus Runde 1, gegen den aktuellen Arbeitsbaum mit Zeilenzahlen neu verifiziert; nicht blockierend)
- Verdict: PASS

## Acceptance criteria
Die Akzeptanzkriterien wurden vollständig in Runde 1 (dokumentiert in `docs/reviews/F18-review-1.md`, Akzeptanztabelle) abgedeckt. Für Runde 2 habe ich selbst verifiziert, dass der reviewed Umfang unverändert geblieben ist:

| Criterion (aus Runde 1, unverändert) | Status | Implementation (file:line, gegen Arbeitsbaum geprüft) | Test (file:method) / Evidence |
|---|---|---|---|
| Nur ein zentraler Reconnect bei mehreren Projekten | PASS (aus Runde 1; Code seitdem unverändert) | `bin/vibe:1357-1402` (`_fritz_auto_coordinated`), `bin/vibe:1136-1162` (Sperre) | `tests/unit/test_fritz_coordination.py:167` `test_simultaneous_projects_share_one_reconnect` (selbst gelesen: 1 Helfer-Aufruf, `state["affected"]`); grün laut `.f18-check/green-tests.log` (Ran 36 / OK) und `.f18-check/full2.log` (749 + 56 Tests, OK, Exit 0) |
| Wartende Projekte starten keinen zweiten Reconnect | PASS | `bin/vibe:1331-1346` (`_fritz_wait_for_result`) | `test_a_waiting_project_never_starts_a_second_reconnect` (Testdatei:209) |
| Alle Projekte informiert / betroffene Projekte wieder anstoßen | PASS | `bin/vibe:1184-1236`; `bin/vibe-run.sh:195-205` (`VIBE_PROJECT="$P"`, Meldung, `sleep 20`) | `test_runner_tells_the_central_reconnect_which_project_continues` (`test_fritz_reconnect.py:668`, selbst gelesen) |
| Fehler-/Schonzeit-/Manuell-/Status-Fälle | PASS | `bin/vibe:1073-1097`, `bin/vibe:1308-1329`, `bin/vibe:1414-1420` | `test_a_failed_reconnect_is_reported_to_all_projects_and_not_repeated`, `test_a_recent_reconnect_is_reused_and_expires`, `test_a_manual_reconnect_participates_in_the_central_control`, `test_status_reports_the_central_result` |
| Dokumentation (F18.md ohne Review-Platzhalter, Reviewdatei laut AGENTS-Workflow) | PASS | `docs/features/F18.md` (199 Zeilen aktuell; Platzhalter entfernt, per grep bestätigt), `docs/reviews/F18-review-1.md` (neu, unveränderter Wortlaut) |-environment Dokumentänderung ohne Codebezug; `bash scripts/verify.sh quick` nach der Änderung Exit 0 (`.f18-check/quick2.log`, selbst gelesen) |

## Findings
- [Minor] `bin/vibe:1148-1149` — EINTR-Zweig umgeht Deadline-Prüfung in `_fritz_lock_acquire`
  - Evidence: `continue` bei `errno.EINTR` springt ohne erneuten `deadline`-Vergleich zum nächsten Sperrversuch; nur bei dauerhaft wiederkehrenden Signalen kann theo­retisch das Wartelimit überschritten werden. Zeilen im aktuellen Arbeitsbaum verifiziert.
  - Required fix: Deadline-Check auch im EINTR-Pfad ausführen (Hinweis aus Runde 1, unverändert gültig).
- [Minor] `bin/vibe:1139-1151` — Degradationspfade der Sperre (`fcntl is None`, nicht-EACCES/EAGAIN) sind dokumentiert, aber ungetestet
  - Evidence: Beide Zweige geben den Handle „best effort" frei; Verhalten ist in `docs/features/F18.md` (Grenzen) beschrieben, ohne eigenen Test. Nicht blockierend, da Verhalten bewusst degradierend und dokumentiert.
  - Required fix: Optional einen Test über Modulinjektion ergänzen oder Doku-Verweis ergänzen.
- [Minor] `bin/vibe:1308-1329` — Manueller Reconnect kann Dashboard-/CLI-Anfrage bis zum Wartezeitlimit blockieren
  - Evidence: Der manuelle Pfad wartet auf die Sperre (`_fritz_wait_seconds`, Default 200+30 s); diese Grenze ist in `docs/features/F5.md` („bis zu drei Minuten") bzw. `docs/features/F18.md` nicht als neue Wartezeit ausgespielt. Bewusste Designentscheidung („ausdrückliche Nutzeraktion"), keine Verletzung eines Akzeptanzkriteriums.
  - Required fix: Hinweis in der Doku ergänzen, dass Dashboard-/CLI-Anfragen im Wartefall länger hängen können.

## Verification
- Change set reviewed: Ausgangscommit `7d4c630660ff42f01ad3a28d25d9094cfa39166e` → Arbeitsbaum (Branch `feature/v-016-lebenszyklus`). Tracked-Diff über `git diff` gesichtet (`bin/vibe`, `bin/vibe-run.sh`, `tests/unit/test_fritz_reconnect.py`, `docs/import-manifest.json`, `docs/baseline.md`, `docs/features/F5.md`, `docs/trilium-index.md`, `FEEDBACK.md`; vorbestehend: `scripts/setup-vibe.py`, `SPEC.md`, `TICKETS.md`, `.vibe/project.env`, PNGs, `tests/unit/test_install_lifecycle.py`). Neue Dateien vollständig gelesen: `tests/unit/test_fritz_coordination.py` (294 Zeilen), `docs/features/F18.md` (299 Zeilen), `docs/reviews/F18-review-1.md` (43 Zeilen).
- Git commands run by me: `git status --short`, `git log --oneline -8`, `git diff 7d4c6306… --stat`, `git diff 7d4c6306… -- <Einzeldateien>`, `git diff --no-index .f18-check/review-diff-1.txt .f18-check/review-diff-2.txt`. Andere Shell-Befehle (`tail`, `ls`, `diff`, `git hash-object`) wurden von der Konfiguration verboten; ich verwendet stattdessen read/grep.
- Schlüsselnachweis der Zweitprüfung: Der Vollständvergleich der beiden Diff-Snapshots zeigt **exakt zwei Änderungen** seit Runde 1: (1) `docs/features/F18.md` 302 → 299 Zeilen (Entfernung des Abschnitts „## Review / Wird nach der unabhängigen Prüfung ergänzt."), (2) Neuaufnahme von `docs/reviews/F18-review-1.md`. Alle `bin/vibe`-, `bin/vibe-run.sh`- und Test-Hunks sind zwischen beiden Snapshots byte-identisch; Stichproben gegen den aktuellen Arbeitsbaum (z. B. `VIBE_PROJECT="$P"`, Testname in Zeile 626/668) stimmen überein. Die behauptete „nur Dokumente"-Änderung ist damit unabhängig bestätigt.
- Logs selbst gelesen: `.f18-check/quick2.log` (Exit 0, 48 Manifestdateien, keine Geheimnisse), `.f18-check/full2.log` (Zeile 786: `Ran 749 tests … OK`, Zeile 851/854: `56 tests … OK`, `Tests erkannt: 805`, Exit 0), `.f18-check/green-tests.log` (Ran 36 / OK), `.f18-check/red-coordination.log` (8 Tests, 6 Failures + 1 Error, konkrete Failing-Assertions). Zusätzlich rote/grüne Kopien stichprobenartig geprüft: `.f18-check/red/bin/vibe` enthält keinen F18-Code, `.f18-check/green/bin/vibe` enthält `_fritz_auto_coordinated` (Zeilen 1357/1402) — Red-first konsequent.
- Minor-Einstufung aus Runde 1 geprüft: Alle drei sind Design-/Robustheits-/Doku-Beobachtungen ohne Verstoß gegen ein Akzeptanzkriterium oder gegen Text aus `SPEC.md`/`AGENTS.md`; je den Review-Regeln blockieren Minors kein PASS.
- Checks not independently run: alle Build-/Test-/Verify-Aufrufe selbst (nur Log-Einsicht); Manifest-Checksummen von `bin/vibe` nicht selbst berechnet; Trilium-Notiz in dieser Runde nicht erneut abgefragt (in Runde 1 vom Reviewer eigenständig verifiziert; seitdem kein Grund zur Änderung sichtbar).
- Important areas inspected: Sperre/Zustand/Wartende/Schonzeit in `bin/vibe`, Läufer-Einbindung in `bin/vibe-run.sh`, neue und geänderte Tests (keine Skips, keine entkräfteten Assertions, echte Prozessintegration mit Attrappen-Helfer), Doku-Zusammenhang (F18.md ↔ F5.md ↔ baseline.md ↔ trilium-index.md).
- Remaining risks: kein echter Router getestet (Attrappe, dokumentiert); zwei Installationen mit getrenntem Zustandsordner koordinieren nicht (dokumentiert); die geänderte F18.md (Platzhalter) und der Reviewbericht sind noch nicht committet — der Commit mit den Nachweisen steht dem Koordinator noch aus.

Die drei Befunde aus Runde 1 sind korrekt als nicht blockierend eingeordnet; durch die Dokumentänderungen wurde keine reviewed Code- oder Testdatei verändert. Verdict: **PASS**.
