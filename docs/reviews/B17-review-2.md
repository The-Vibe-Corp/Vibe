# B17 — Review Runde 2

Datum: 19.11.2026
Reviewer: code-reviewer (unabhängig, read-only)
Stand: Branch `feature/m0p/b17-instanz-isolation`, Änderungssatz `8b07828..f589acb`
(Runde-1-Umsetzung `1ecfb1d..f589acb`); Arbeitskopie laut `git status --short`
sauber, HEAD `f589acb`. Vorgänger: docs/reviews/B17-review-1.md
(Verdict: CHANGES REQUIRED). Hinweis des Reviewers: Schrittlimit erreicht;
ein `git diff`/`git show` war nicht mehr möglich, die relevanten Dateien
wurden vollständig gelesen.

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 1
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| R1-F1 (High): Android-Abschlussprüfung läuft in bereinigter Umgebung und Sandbox | PASS | `bin/vibe-run.sh:418-427` (`verify_run`), `:437-439` (Android-Zweig nutzt `verify_run`) | `tests/unit/test_b17_runner_isolation.py::test_android_final_verification_runs_in_the_sandbox_with_clean_environment` (3 echte `subTest`s); Bericht §5.8.1 zeigt den Rotbeleg (3 Failures), grüner Lauf (`Ran 7 tests, OK`) nur als Agentenmeldung geliefert, nicht unabhängig ausgeführt |
| R1-F2 (Medium): Fortsetzungsbefehle nennen den effektiven `--runtime` | FAIL (teilweise) | `bin/vibe:5533-5543` (`_ask_timeout`/`_ask_autonomous`) korrekt; weiterhin ohne `--runtime`: `bin/vibe:5600`, `bin/vibe_packages.py:820-824`, `:961-965` | `tests/unit/test_b17_questions_runtime.py::test_timeout_and_autonomous_hints_name_the_given_runtime` (2 echte `subTest`s) deckt nur die beiden Helfer ab; Bericht §5.8.2 Rotbeleg; grüner Lauf (`Ran 5 tests, OK`) nur als Agentenmeldung |
| R1-F3 (Medium): Guard greift bei explizitem `--install` auf die laufende Installation | PASS | `scripts/setup-vibe.py:1443-1459` (`explicit_running` über `VIBE_INSTALL`) | `tests/unit/test_b17_isolation.py::UpdateGuardTest::test_update_with_an_explicit_install_on_the_running_instance_is_refused` (A3a) und `::test_update_with_an_explicit_install_and_source_is_allowed` (A3b); Bericht §5.8.3 Rotbeleg A3a; grüner Lauf (`Ran 12 tests, OK`) nur als Agentenmeldung |
| R1-F4 (Medium): Grüner AK4-Nachweis für die drei Setup-Module | PASS | `tests/unit/test_ap04_setup_harness.py`, `test_setup_vibe.py`, `test_install_lifecycle.py` mit `environ=`/Temp-Pfaden | Bericht §5.8.4: `test_ap04_setup_harness` `Ran 6 tests, OK`; verbleibende Reds klar als `_toolchain`-/`register_projects`-Baseline getrennt (Zeilen 499-534) |
| Testintegrität der drei neuen Fälle | PASS | — | Keine leeren Körper, keine `skip`/`assume`-Marker, keine nicht-falsifizierbaren Assertions; vorhandene Assertions nicht abgeschwächt (nur Isolationsparameter ergänzt) |
| AK7 gesamt: Rückfragen ohne Produktivpfad | FAIL | Prompt-Hinweis `bin/vibe-run.sh:374-378` korrekt; Optionspfad `bin/vibe:5565-5566`, `:5615` korrekt; Resthinweise siehe Finding 1 | Prompt-Test `test_b17_runner_isolation.py` sowie `test_cmd_ask_writes_into_the_given_runtime`/`test_cmd_answer_uses_the_given_runtime`; die verbleibenden Hinweise sind ungetestet |

## Findings

- [Medium] `bin/vibe:5600` (zusätzlich `bin/vibe_packages.py:820-824` und `:961-965`) — verbleibende Fortsetzungs-/Antworthinweise nennen `--runtime` weiterhin nicht
  - Evidence: `cmd_ask` gibt nach dem Anlegen einer Frage aus: `"vibe answer " + qid + " ..."` ohne Laufzeitordner. `cmd_answer` setzt ohne Option `runtime = LOGS` (`bin/vibe:5615`), `LOGS = PATHS.runtime` (`bin/vibe:90`), also den Produktiv-Laufzeitordner aus der Nutzerkonfiguration. In einem Lauf mit bereinigter Umgebung (kein `VIBE_RUNTIME`) zeigt der ausgegebene Befehl damit nicht auf den Laufzeitordner der Frage. Dasselbe Muster liegt in den PREFLIGHT-/BARRIER-Hinweisen von `vibe_packages.py` vor, obwohl der Läufer den Laufzeitordner bereits übergibt (`bin/vibe-run.sh:839`, `--runtime "$RUNTIME"`). Der neue Test `test_timeout_and_autonomous_hints_name_the_given_runtime` prüft ausschließlich `_ask_timeout`/`_ask_autonomous`, sodass diese Pfade ungetestet bleiben. Der Round-1-Befund ist damit an zwei der drei Meldungsstellen behoben, die Ursache (selbst erzeugter Befehl ohne Laufzeitordner) besteht an den übrigen Stellen fort.
  - Required fix: Alle vom Werkzeug ausgegebenen Fortsetzungs-/Antwortbefehle (`cmd_ask`-Erzeugungsmeldung, PREFLIGHT- und BARRIER-Hinweis) mit dem effektiven `runtime` als `--runtime <pfad>` ausgeben und die Testabdeckung auf diese Ausgaben erweitern; alternativ die verbleibenden Meldungen ausdrücklich als reine Nutzerhinweise kennzeichnen und belegen, dass der Dashboard-Pfad den isolierten Laufzeitordner korrekt adressiert.

- [Minor] `docs/reviews/B17-test-agent-report.md:408-487` — Abschnitt 5.8 enthält für die drei neuen Reviewfälle nur Rotbelege, keinen grünen Lauf
  - Evidence: §5.8.1-5.8.3 zeigen ausschließlich `FAILED`-Ausgaben; grüne Ergebnisse (`runner 7 OK`, `questions_runtime 5 OK`, `isolation 12 OK`) wurden nur in der Agentenmeldung berichtet und sind nicht im Artefakt dokumentiert. §5.8.4 belegt grün nur AK4. Die Überschrift „Grünnachweis AK4 und Reviewfälle“ deckt die drei Reviewfälle damit nicht ab.
  - Required fix: Die tatsächlichen grünen Laufausgaben der drei Module nach der Implementierung in §5.8.1-5.8.3 ergänzen (Befehl, Zähler, `OK`).

## Bewertung der Restrisiken (Voten)

1. **`bash -lc` in `bin/vibe-run.sh:420`:** Das Risiko bleibt real — Login-Profile können `VIBE_*` erneut exportieren und die Bereinigung aufheben; die Tests nutzen ein leeres Temp-`HOME` und erkennen das nicht. Es ist nicht durch dieses Arbeitspaket verursacht und in `docs/betrieb.md:209-224` nicht als Grenze dokumentiert. **Votum: akzeptiertes Restrisiko, nicht blockierend** — Empfehlung als Folgemaßnahme (`bash -c` oder Nachbereinigung nach Profilstart plus Test mit re-exportierendem Profil).
2. **Pi-`--agents-dir`-Argv in `bin/vibe-run.sh:545`:** Ein Produktivpfad wird als Argument an die Harness-CLI übergeben; funktional für Rollenmetadaten plausibel und innerhalb der Sandbox, aber nicht testabgedeckt. **Votum: akzeptiertes Design-Risiko, nicht blockierend** — Empfehlung: Argument im Runner-Test explizit prüfen oder die Notwendigkeit dokumentieren.
3. **Guard-Grenze ohne `VIBE_INSTALL`:** Ein explizites `--install` auf eine vorhandene Installation bleibt ohne `--source` möglich, wenn `VIBE_INSTALL` nicht gesetzt ist (`scripts/setup-vibe.py:1443-1449`). Das entspricht der dokumentierten Grenze (`docs/betrieb.md:194-202`) und der Formulierung „erkannte laufende Installation“ aus Review 1. **Votum: akzeptiert und dokumentiert, nicht blockierend.**

## Verification
- Change set reviewed: `8b07828..f589acb`; Arbeitskopie laut `git status --short` sauber, HEAD `f589acb`. Ein `git diff` konnte nicht mehr ausgeführt werden (Schrittlimit); die relevanten Dateien wurden vollständig gelesen.
- Git commands run by me: `git status --short`, `git log --oneline -8`. Kein `git diff`/`git show`.
- Checks with supplied output: Bericht §5.8.1 (Rot: `Ran 7 tests`, 3 Failures), §5.8.2 (Rot: `Ran 5 tests`, 2 Failures), §5.8.3 (Rot: `Ran 12 tests`, 1 Failure), §5.8.4 (Grün: `test_ap04_setup_harness` `Ran 6 tests, OK`); grüne Läufe der drei Reviewfall-Module nur als Agentenmeldung (7/5/12 OK).
- Checks not independently run: alle Build-, Test-, Syntax-, Secret- und Import-Manifest-Prüfungen.
- Important areas inspected: `bin/vibe-run.sh` (360-443, 525-569, 839), `bin/vibe` (5513-5642), `bin/vibe_packages.py` (810-839, 948-977), `scripts/setup-vibe.py` (1425-1484), `docs/betrieb.md` (185-229), `FEEDBACK.md` (639-651), `docs/reviews/B17-review-1.md`, `docs/reviews/B17-test-agent-report.md` (330-620), `tests/unit/test_b17_runner_isolation.py`, `test_b17_questions_runtime.py`, `test_b17_isolation.py`, `test_ap04_setup_harness.py`.
- Remaining risks: Siehe Restrisiken 1-3; zusätzlich ist die Vollständigkeit des Diffs ohne `git diff` nicht abschließend belegt.

**Verdict: CHANGES REQUIRED**
