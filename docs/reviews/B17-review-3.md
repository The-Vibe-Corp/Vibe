# B17 — Review Runde 3 (Abschluss)

Datum: 19.11.2026
Reviewer: code-reviewer (unabhängig, read-only)
Stand: Branch `feature/m0p/b17-instanz-isolation`, HEAD `6eeb9a4`
(Runde-2-Umsetzung `a1217fa..6eeb9a4`; Gesamtänderungssatz `8b07828..6eeb9a4`).
Vorgänger: docs/reviews/B17-review-1.md (CHANGES REQUIRED, umgesetzt in
`f589acb`), docs/reviews/B17-review-2.md (CHANGES REQUIRED, umgesetzt in
`6eeb9a4`). Hinweis des Reviewers: Shell war gesperrt; HEAD/Branch aus
`.git/worktrees/…` und `logs/HEAD` gelesen, kein `git diff` möglich — die im
Auftrag genannten Dateien wurden vollständig gelesen.

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Bewertung der Runde-2-Befunde

- **R2-Medium (verbleibende Antwort-/Fortsetzungshinweise): PASS.**
  Die drei beanstandeten Stellen nennen jetzt den effektiven Laufzeitordner:
  `bin/vibe:5600-5601` (`cmd_ask`-Erzeugungsmeldung), `bin/vibe_packages.py:820-824` (PREFLIGHT) und `bin/vibe_packages.py:961-965` (BARRIER). Die Tests prüfen genau diese Ausgaben: `tests/unit/test_b17_questions_runtime.py:216-233` (`subTest(hint="creation")`) sowie `:256-294` (`PackageHintRuntimeTest`, `subTest` `preflight`/`barrier`). Die Assertions sind falsifizierbar; der Rotbeleg in `docs/reviews/B17-test-agent-report.md:640-657` zeigt die drei Fehlschläge vor der Änderung. Der Grünlauf des aktuellen 6-Test-Stands ist allerdings nur als Agentenmeldung vorhanden und nicht im Artefakt dokumentiert (Minor 1).

- **R2-Minor (grüne Laufausgaben in §5.8.1–5.8.3): PASS.**
  §5.8.1 (`docs/reviews/B17-test-agent-report.md:443-461`) nennt Befehl, `Ran 7 tests`, `OK` und Stand `f589acb`; §5.8.2 (`:489-505`) nennt `Ran 5 tests`, `OK` und ausdrücklich „vor den Ergänzungen aus Review 2“; §5.8.3 (`:534-549`) nennt `Ran 12 tests`, `OK` und Stand `f589acb`. Die geforderten Grünnachweise der drei Reviewfälle stehen damit im Artefakt. Die Einschränkung, dass §5.8.2 den Stand vor der Runde-2-Erweiterung zeigt, ist zutreffend gekennzeichnet und wird durch Minor 1 für den neuen Teststand ergänzt.

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| R2-Medium: `cmd_ask`-Erzeugungsmeldung, PREFLIGHT- und BARRIER-Hinweis nennen den effektiven `--runtime`; Testabdeckung dieser Ausgaben | PASS | `bin/vibe:5600-5601`; `bin/vibe_packages.py:820-824`, `:961-965` | `tests/unit/test_b17_questions_runtime.py::QuestionRuntimeTest.test_timeout_and_autonomous_hints_name_the_given_runtime` (`subTest hint="creation"`, `:216-233`); `::PackageHintRuntimeTest.test_preflight_and_barrier_hints_name_the_given_runtime` (`:256-294`); Bericht §5.8.5 (`:603-669`) mit Rotbeleg `Ran 6 tests`, `FAILED (failures=3)`; grüner 6-Test-Lauf nur als Agentenmeldung, nicht im Artefakt |
| R2-Minor: §5.8.1–5.8.3 enthalten grüne Läufe mit Befehl, Zähler, `OK`, Stand | PASS | — | Bericht §5.8.1 (`:443-461`, `Ran 7 tests`, `OK`), §5.8.2 (`:489-505`, `Ran 5 tests`, `OK`, Stand `f589acb`), §5.8.3 (`:534-549`, `Ran 12 tests`, `OK`) |
| Testintegrität des Deltas: echte Assertions, keine Abschwächung, keine Skips/Mocks, Rotbeleg | PASS | — | `tests/unit/test_b17_questions_runtime.py:216-233`, `:256-294`: reale `cmd_ask`-/`assist_preflight`-/`assist_barrier`-Aufrufe, `redirect_stdout`, `timeout=0`, keine `skip`/`assume`-Marker, keine Mock-Ersetzung des Prüfverhaltens; bestehende Timeout-/Autonomie-Assertions unverändert, neuer `creation`-`subTest` additiv; Rotbeleg §5.8.5 |
| Gesamtblick: keine neuen Critical/High/Medium; Runde-1-Fixes und drei Restrisiken unverändert | PASS | Android-Prüfung weiterhin über `verify_run` (`bin/vibe-run.sh:437-439`), Guard weiterhin `scripts/setup-vibe.py:1443-1459`, Prompt-Runtime `bin/vibe-run.sh:378`; Restrisiken siehe unten | Die gelesenen Stellen sind gegenüber Runde 2 unverändert; Delta betrifft die drei Meldungsstellen, den Test und die Berichte. Kein neuer Critical/High/Medium-Befund |

## Findings

- [Minor] `docs/reviews/B17-test-agent-report.md:603-669` — Grünlauf der in Runde 2 ergänzten Tests fehlt; Testinventar und Zähler sind nicht auf den neuen Stand gezogen
  - Evidence: §5.8.5 dokumentiert für `tests.unit.test_b17_questions_runtime` nur den Rotlauf `Ran 6 tests in 0.063s` und `FAILED (failures=3)` (`:640-657`); ein grüner Lauf `Ran 6 tests`, `OK` für den Stand nach der Runde-2-Änderung fehlt. Der grüne Lauf in §5.8.2 (`:489-505`) ist ausdrücklich „vor den Ergänzungen aus Review 2“ und zählt `Ran 5 tests`. Zusätzlich listet §4.2 (`:110-122`) weiterhin nur vier Fälle, und §1 (`:13`) spricht von „24 neuen Testfällen“, obwohl die vier B17-Module im gelesenen Stand 29 Tests enthalten (12 + 6 + 4 + 7). Der vom Umsetzer berichtete Lauf „questions_runtime 6 OK“ ist damit nicht im Artefakt belegt.
  - Required fix: Den tatsächlichen grünen Lauf des aktuellen `tests.unit.test_b17_questions_runtime` (Befehl mit `env -u`-Präfix, `Ran 6 tests`, `OK`, Stand/Commit) in §5.8.5 ergänzen und §1/§4.2 auf den aktuellen Testumfang fortschreiben.

- [Minor] `docs/import-manifest.json:973-987` — B17-Dateiliste nennt `bin/vibe_packages.py` nicht, obwohl das Delta diese Datei ändert
  - Evidence: Das B17-Objekt listet in `dateien` (`:975-984`) zehn Dateien, darunter `bin/vibe`, `bin/vibe-run.sh` und `bin/vibe_sandbox.py`, aber nicht `bin/vibe_packages.py`. Der `grund` desselben Eintrags (`:987`) beschreibt ausdrücklich die Runde-2-Änderung an den PREFLIGHT-/BARRIER-Hinweisen in `vibe_packages.py`; der zugehörige `files`-Eintrag existiert unter `:1061-1065`. Die geänderte Datei ist damit nicht dem B17-Paket zugeordnet; die Formulierung „zehn geänderte files-Einträge“ passt nicht, wenn der Eintrag für `vibe_packages.py` aktualisiert wurde.
  - Required fix: `bin/vibe_packages.py` in die B17-`dateien`-Liste aufnehmen und den zugehörigen Größen-/SHA-Eintrag auf dem aktuellen Stand halten; Manifest-Prüfung erneut ausführen.

## Testintegrität des Deltas
- Keine leeren Testkörper, keine `skip`/`assume`/`expectedFailure`-Marker, keine nicht-falsifizierbaren Assertions und keine Mocks in `tests/unit/test_b17_questions_runtime.py`.
- Die neuen Fälle rufen die realen Funktionen auf: `cmd_ask` über `self.cli`, `assist_preflight`/`assist_barrier` direkt mit `redirect_stdout` und `timeout=0`; die geprüften Zeilen stammen aus dem echten Produktionspfad.
- Die bestehenden Timeout-/Autonomie-Assertions wurden nicht abgeschwächt; der `creation`-Fall ist additiv. Der Rotbeleg zeigt die drei erwarteten Fehlschläge vor der Änderung.
- Einschränkung: Der Grünlauf des neuen 6-Test-Stands ist nicht im Bericht dokumentiert (Minor 1); die Testimplementierung selbst ist nicht zu beanstanden.

## Verification
- Change set reviewed: `a1217fa..6eeb9a4` (Runde-2-Umsetzung) und `8b07828..6eeb9a4` (Gesamtstand), abgegrenzt anhand des Arbeitsauftrags und des Reflogs. Ein `git diff` war nicht möglich. Die im Auftrag genannten Dateien wurden vollständig gelesen: `bin/vibe`, `bin/vibe_packages.py`, `tests/unit/test_b17_questions_runtime.py`, `docs/reviews/B17-test-agent-report.md`, `docs/import-manifest.json`.
- Git commands run by me: keine. `git status --short` und `git log` wurden mit `Permission denied: shell` abgewiesen. HEAD und Branch wurden aus `.git/worktrees/vibe-B17-m3QD8S/HEAD` und `logs/HEAD` gelesen: Branch `feature/m0p/b17-instanz-isolation`, HEAD `6eeb9a4`. Die Sauberkeit der Arbeitskopie ist damit nicht unabhängig bestätigt; der untracked Entwurf `docs/features/B17.md` wurde auftragsgemäß nicht bewertet.
- Checks with supplied output: Bericht §5.8.1 `Ran 7 tests ... OK`, §5.8.2 `Ran 5 tests ... OK` (Stand `f589acb`, vor Runde-2-Ergänzungen), §5.8.3 `Ran 12 tests ... OK`; §5.8.5 `Ran 6 tests ... FAILED (failures=3)` als Rotbeleg. Vom Umsetzer nur berichtet, nicht artefaktisch belegt: `questions_runtime 6 OK`, `runner 7 OK`, `isolation 12 OK`, `questions 35 OK`, `ap10_gates 34 OK`, `f21 22 OK`, `b9 18 OK`, `pause 16 OK`, `f22 1` vorbestehender Error, Manifest 57 OK, Syntax OK, Secrets OK, `config.json`-MD5 unverändert.
- Checks not independently run: alle Build-, Test-, Syntax-, Secret- und Manifest-Prüfungen; Shell war gesperrt.
- Important areas inspected: `bin/vibe` (5513-5678), `bin/vibe_packages.py` (617-687, 780-999, 1455-1582), `bin/vibe-run.sh` (360-439, 820-849), `tests/unit/test_b17_questions_runtime.py`, `tests/unit/test_b17_runner_isolation.py` (425-464), `tests/unit/test_b17_isolation.py`, `docs/reviews/B17-review-1.md`, `docs/reviews/B17-review-2.md`, `docs/reviews/B17-test-agent-report.md` (1-175, 330-750), `docs/betrieb.md` (185-229), `scripts/setup-vibe.py` (1415-1489), `docs/import-manifest.json` (972-1065), `templates/*/AGENTS.md` und der `GENERAL_RULES`-Block in `bin/vibe`.
- Remaining risks:
  1. **`bash -lc` in `bin/vibe-run.sh:420`:** Login-Profile können `VIBE_*` erneut exportieren; die Tests nutzen ein leeres Temp-`HOME`. Weiterhin nur im Reviewbericht, nicht in `docs/betrieb.md` als Grenze dokumentiert. **Votum unverändert: akzeptiertes Restrisiko, nicht blockierend.**
  2. **Pi-`--agents-dir`-Argv in `bin/vibe-run.sh:545`:** Ein Produktivpfad wird an die Harness-CLI übergeben; funktional plausibel, nicht testabgedeckt. **Votum unverändert: akzeptiertes Design-Risiko, nicht blockierend.**
  3. **Guard-Grenze ohne `VIBE_INSTALL`:** Ein explizites `--install` auf eine vorhandene Installation bleibt ohne `--source` möglich, wenn `VIBE_INSTALL` nicht gesetzt ist (`scripts/setup-vibe.py:1443-1449`); dokumentiert in `docs/betrieb.md:194-202`. **Votum unverändert: akzeptiert und dokumentiert, nicht blockierend.**
- Zusätzliche Einschränkung: Ohne `git diff` ist die Vollständigkeit des Delta-Dateisatzes nicht unabhängig belegt; die im Auftrag genannten Dateien und die drei Meldungsstellen wurden jedoch vollständig gelesen. Die beiden Minor-Befunde betreffen Dokumentations-/Nachweissynchronisation, nicht die Funktionsfähigkeit.

**Verdict: PASS**
