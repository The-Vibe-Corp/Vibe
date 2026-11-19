# B17 — Review Runde 1

Datum: 19.11.2026
Reviewer: code-reviewer (unabhängig, read-only)
Stand: Branch `feature/m0p/b17-instanz-isolation`, Änderungssatz `8b07828..4cd5260`
(Commits f11f070, 69318e0, bd7e6ee, 4cd5260; Arbeitskopie sauber).
Rotphase und Fallbeschreibungen: `docs/reviews/B17-test-agent-report.md`.

## Summary
- Critical: 0
- High: 1
- Medium: 3
- Minor: 0
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: `setup.main(..., environ=...)`; alle Pfade aus übergebener Umgebung | PASS | `scripts/setup-vibe.py:1420-1427` (Logs/Defaults aus `environ`), Guard nutzt `environ`-Target | `test_b17_isolation.py::MainEnvironTest.*`; Bericht §5.7 `Ran 10 tests, OK` (nur berichtet) |
| AK2: `--update` auf laufende Instanz nur mit autorisierter Quelle | FAIL | `scripts/setup-vibe.py:1440-1451` — Guard greift nur ohne `--install` | `test_b17_isolation.py::UpdateGuardTest.*` deckt nur implizites Ziel; explizites `--install` auf dasselbe Ziel ungetestet (Finding 3) |
| AK3: Klare Quelle `--source`, Verwendung + `version.json` | PASS | `scripts/setup-vibe.py` Source-Auflösung; `install-vibe.sh` mit `--source "$KIT"` | `test_b17_isolation.py::SourceOptionTest.*` (inkl. defekter Quelle); §5.7 `OK` |
| AK4: Tests übergeben bereinigte Umgebung und explizite Temp-Pfade | NOT VERIFIED | `test_ap04_setup_harness.py`, `test_setup_vibe.py`, `test_install_lifecycle.py` (laut Bericht §4.5) | Kein grüner Lauf nach Implementierung belegt: §5.5/5.6 rot, §5.7 listet die drei Module nicht (Finding 4) |
| AK5: Regressionstest Test-`--update` schreibt nur Temp-Pfade | PASS | `scripts/setup-vibe.py` Installationsplan | `test_b17_isolation.py::IsolatedUpdateTest.*`; §5.7 `OK` (berichtet) |
| AK6: Läufer startet Agenten ohne Produktivpfade | PASS | `bin/vibe-run.sh:41` (`VIBE_CLEAN_ENV`), `:543`, `:553` | `test_b17_runner_isolation.py::AgentEnvironmentTest.*`; §5.7 `Ran 6 tests, OK` |
| AK7: Rückfragen des Agenten ohne Produktivpfad | FAIL | `bin/vibe-run.sh:378` (Prompt korrekt), aber `bin/vibe:5533-5543` Fortsetzungsbefehle ohne `--runtime`, Default `LOGS = PATHS.runtime` (`bin/vibe:90`, `:5559`, `:5615`) | `test_b17_runner_isolation.py:307-314` (Prompt) und `test_b17_questions_runtime.py::*` grün; die vom Werkzeug ausgegebenen Fortsetzungsbefehle sind nicht abgedeckt (Finding 2) |
| AK8: Sandbox gilt für Agent **und** Prüfungen | FAIL | `bin/vibe-run.sh:418-427` (generisch) vs. `:437` Android-Direktaufruf ohne Clean-Env/Sandbox/`VIBE_VERIFY_RUNTIME` | `test_b17_runner_isolation.py:359-383` nur generischer `VERIFY_FULL`; kein Android-Fall (Finding 1) |
| AK9: Ohne neue Angaben bisheriges Verhalten | PASS | `bin/vibe_sandbox.py` `bwrap_argv` Standardbindungen | `test_b17_sandbox_argv.py::test_without_new_arguments_the_previous_behaviour_stays`; §5.7 `OK` |

## Findings

- [High] `bin/vibe-run.sh:437` — Android-Abschlussprüfung umgeht die gesamte B17-Isolation
  - Evidence: `final_verify` ruft bei leerem `VERIFY_FULL` für `TYPE=android` direkt `bash "$V/verify.sh" "$P" full` auf. Damit fehlen gleichzeitig `verify_run` (`:418`), die bereinigte Umgebung `VIBE_CLEAN_ENV` (`:41`), `VIBE_VERIFY_RUNTIME` (`:420`) und der Sandbox-Wrapper (`:421-423`). Der Prozess erbt die Runner-Umgebung inklusive produktiver `VIBE_*`-Pfade und kann die laufende Instanz verändern — genau der in B17 adressierte Vorfall. `test_b17_runner_isolation.py:359` prüft ausschließlich den generischen `VERIFY_FULL`-Pfad; ein Android-Lauf ohne `VERIFY_FULL` ist nicht abgedeckt. Zusätzlich fehlt dort `VIBE_VERIFY_RUNTIME`, das die angepassten Fixtures (`test_b9_self_repair.py:72`) erwarten.
  - Required fix: Den Android-Zweig über denselben bereinigten, sandboxed Prüfadapter führen (Clean-Env + Sandbox + `VIBE_VERIFY_RUNTIME`) und einen Test ergänzen, der einen `TYPE=android`-Lauf ohne `VERIFY_FULL` abdeckt.

- [Medium] `bin/vibe:5533-5543` — selbst erzeugte Fortsetzungsbefehle nennen kein `--runtime`
  - Evidence: `_ask_timeout` gibt `vibe ask --wait <id> --timeout …` aus, `_ask_autonomous` `vibe answer <id> … --by agent` — beide ohne `--runtime`. `cmd_ask`/`cmd_answer` setzen `runtime = LOGS` (`:5559`, `:5615`) und `LOGS = PATHS.runtime` (`:90`), also den Produktiv-Laufzeitordner aus der Nutzerkonfiguration, wenn `VIBE_RUNTIME` fehlt. Im bereinigten Agentenlauf fehlt `VIBE_RUNTIME`; ein Agent, der die ausgegebene Zeile wörtlich befolgt, schreibt/liest den Produktivpfad. Der Prompt-Hinweis (`bin/vibe-run.sh:374-378`) ist korrekt und getestet, die Laufzeitmeldungen des Werkzeugs selbst sind es nicht; `test_b17_questions_runtime.py` prüft sie nicht.
  - Required fix: In beiden Meldungen den effektiven `runtime` als `--runtime <pfad>` mitschreiben und einen Test ergänzen, der die ausgegebene Fortsetzungszeile bei abweichendem `runtime` prüft.

- [Medium] `scripts/setup-vibe.py:1440` — Guard lässt ein explizites `--install` auf dasselbe laufende Ziel ohne `--source` zu
  - Evidence: Die Bedingung `options.update and not options.source and not options.install and detect_existing(target)["toolchain"]` schließt jedes `--install` aus. `--update --install <laufende Installation>` überspringt den Schutz und schreibt in die laufende Instanz, obwohl keine autorisierte Quelle angegeben ist. `test_b17_isolation.py::UpdateGuardTest.*` deckt nur das implizit aufgelöste Ziel ab; `docs/betrieb.md` dokumentiert die Ausnahme, hebt die Anforderung „nur mit autorisierten Quelle“ für diesen Pfad aber nicht auf.
  - Required fix: Den Guard auch bei explizitem `--install` greifen lassen, wenn das Ziel der erkannten laufenden Installation entspricht (oder `--source` verlangen, sobald Ziel = laufende Installation), plus Testfall.

- [Medium] `docs/reviews/B17-test-agent-report.md` (Abschnitt 5.7) / AK4 — kein grüner Nachweis für die drei angepassten Setup-Module
  - Evidence: §5.5 und §5.6 belegen nur die Rotphase von `test_ap04_setup_harness`, `test_setup_vibe`, `test_install_lifecycle`. §5.7 (Läufe nach der Implementierung) listet ausschließlich `test_b9_self_repair`, `test_pause_after_package`, die vier B17-Module, `test_questions` und `test_runner_package_gates`. Für die drei AK4-Module existiert nach der Implementierung kein `OK`; §6 bestätigt fortbestehende Baseline-Reds (u. a. `TypeError: register_projects() missing 1 required positional argument`). Damit ist die AK4-Forderung „Tests laufen mit bereinigter Umgebung und expliziten Temp-Pfaden“ nicht nachgewiesen.
  - Required fix: Die drei Module nach der Implementierung mit dem `env -u`-Präfix ausführen, Ergebnisse mit klarer Trennung B17-bedingter Fehler von Baseline-Reds dokumentieren.

## Bewertung der bewussten Entscheidungen

1. **Guard-Grenze (`--install` befreit):** nachvollziehbar für abweichende Temp-Ziele, aber als Nebenwirkung umgehbar (Finding 3). Die Ausnahme ist dokumentiert, nicht versteckt — dennoch offen gegenüber der Ticketformulierung.
2. **`--source`-Vorrang:** plausibel und getestet (`SourceOptionTest`, inkl. defekter Quelle); `version.json.source` nachvollziehbar.
3. **`--skip-deps` ohne Exit 2:** konsistent mit `docs/betrieb.md:224-228`; keine Shell-Stelle gefunden, die auf Exit 2 angewiesen wäre. Akzeptabel.
4. **`VIBE_VERIFY_RUNTIME` nur pro Prüfaufruf:** saubere Trennung, aber sie macht den Android-Direktpfad (`:437`) zum Bruch — dort fehlt die Variable (Finding 1).
5. **`QUESTION_HINT`-Kurzform + `--runtime`-Zusatz:** im Prompt korrekt (`:374-378`) und getestet; die Laufzeitmeldungen des Werkzeugs bleiben dahinter zurück (Finding 2).
6. **`final_verify` Schreibzugriff auf das Projekt:** im Sandbox-Argv nachvollziehbar; das Projekt ist ohnehin per Standardbindung schreibbar (`test_b17_runner_isolation.py:348`), daher kein zusätzlicher Befund.
7. **Fixture-Anpassungen (`VIBE_VERIFY_RUNTIME`, `FAKE_RUNTIME`):** keine Assertion abgeschwächt; nur Variablenname/Pfadträger geändert (`test_b9_self_repair.py:72`, `runner_support.py:406-412`, `test_pause_after_package.py:353-359`).
8. **Sandbox-Argv:** `--chdir` auf Arbeitskopie, Arbeitskopie/Konfigurationsprojekt schreibbar, `.vibe` schreibgeschützt (`bin/vibe_sandbox.py`); durch `test_b17_sandbox_argv.py` und `test_b17_runner_isolation.py:320-357` gedeckt.

## Testintegrität

- Keine leeren Testkörper, keine `skip`/`assume`-Marker und keine nicht-falsifizierbaren Assertions in den vier B17-Modulen gefunden.
- Die drei Fixture-Anpassungen sind reine Isolationsmaßnahmen; Markerpfade und Assertions bleiben inhaltlich gleich.
- Die Rotphase ist im Bericht §5.6 mit Befehlen, Zählern und Ursachen belegt (geliefert, nicht unabhängig reproduziert).
- Positiv: Die bestehenden Anker `test_questions` (`35, OK`) und `test_runner_package_gates` (`12, OK`) sind unverändert.
- Einschränkung: Für AK4 existiert kein grüner Nachweis (Finding 4).

## Verification
- Hinweis: Die maximale Schrittzahl war erreicht; alle Shell-Aufrufe waren zusätzlich durch `Permission denied: shell` gesperrt. Es wurde kein Git-, Build- oder Testbefehl ausgeführt; das Review ist lesebasiert.
- Change set reviewed: **nicht per Git abgegrenzt** — die Commitfolge stammt aus dem Arbeitsauftrag, nicht aus eigener Git-Ausgabe.
- Git commands run by me: keine (Berechtigung verweigert).
- Checks with supplied output: Bericht §5.6/§5.7 (`test_b17_isolation` 10 OK, `test_b17_questions_runtime` 4 OK, `test_b17_sandbox_argv` 4 OK, `test_b17_runner_isolation` 6 OK, `test_b9_self_repair` 18 OK, `test_pause_after_package` 16 OK, `test_questions` 35 OK, `test_runner_package_gates` 12 OK) — **nur berichtet**.
- Checks not independently run: alle Tests, `scripts/check-syntax.py`, `scripts/check-no-secrets.py`, `scripts/check-import-manifest.py`, Hash-/Größenprüfung der `docs/import-manifest.json`-Einträge.
- Important areas inspected: `bin/vibe-run.sh` (41, 140-233, 365-440, 500-575), `bin/vibe` (85-142, 5520-5642), `bin/vibe_sandbox.py`, `scripts/setup-vibe.py` (1420-1532), `install-vibe.sh`, `tests/unit/test_b17_*.py`, `tests/unit/runner_support.py`, `test_b9_self_repair.py`, `test_pause_after_package.py`, `docs/betrieb.md` (185-228), `docs/reviews/B17-test-agent-report.md`, `docs/import-manifest.json` (973-987), `FEEDBACK.md` (B17), `templates/*/AGENTS.md`.
- Remaining risks:
  - `bin/vibe-run.sh:420` verwendet `bash -lc`; Login-Profile können `VIBE_*` erneut exportieren und die Bereinigung aufheben. Die Tests nutzen ein leeres Temp-`HOME` ohne Profilskripte und können das nicht erkennen.
  - `bin/vibe-run.sh:542` gibt `VIBE_AGENTS_DIR` als `--agents-dir` an den Pi-Harness weiter; funktional plausibel (Rollenmetadaten), aber ein Produktivpfad im Argv und nicht durch einen Test abgedeckt.
  - `docs/import-manifest.json:973-987` behauptet aktualisierte Hashes/Größen; ohne `check-import-manifest.py` nicht bestätigt.
  - Die drei AK4-Module bleiben ohne grünen Nachweis; Baseline-Reds dürfen nicht mit B17-Isolation verwechselt werden.
  - Da das Change Set nicht per Git abgegrenzt werden konnte, ist die Vollständigkeit der geprüften Dateimenge nicht gesichert.

**Verdict: CHANGES REQUIRED**
