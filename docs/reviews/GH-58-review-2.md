# GH-58 — Review Runde 2 (unabhängiger Review-Agent)

Arbeitspaket: GH-58 — Autonomer Modus Einstellung wird ignoriert (GitHub #58)
Branch: feature/m0p/gh-58
Geprüfter Stand: Arbeitsbaum, uncommittet nach den Runde-1-Fixes (M1/M2/L2, H1/H2-Nachweise)
Datum: 2026-11-24
Prüfer: unabhängiger Review-Agent (Code-Review, schreib- und shell-frei; nur Lesezugriff)

## Summary

- Critical: 0
- High: 0
- Medium: 1
- Minor: 2
- Verdict: FAIL (nur wegen des Medium-Befunds zur unvollständigen i18n-/Textumstellung; alle High-Befunde aus Runde 1 sind behoben, alle Ticketkriterien sind umgesetzt und mit Testfällen unterlegt)

## Prüfungsumfang / Methode

- **Selbst geprüft (Dateilektüre):** `bin/vibe` (6500–6722), `bin/vibe_questions.py` (vollständig), `bin/vibe_autonomous.py` (vollständig), `bin/vibe_packages.py` (Fundstellen), `bin/vibe_runs.py` (1214–1335), `bin/vibe-web.py` (575–647, 1600–1620, 2098–2156), `bin/vibe-run.sh` (421–427), `bin/web/nova-project.js` (695–739, 1876–1955), `bin/web/app.js` (230–260, 405–414), `bin/web/i18n.js` (1–50, 1135–1165, 2197–2213), `docs/features/GH-58.md`, `docs/features/F16.md` (40–124), `docs/features/F33.md` (225–235), `docs/reviews/GH-58-test-agent-report.md`, `docs/reviews/GH-58-review-1.md`, Tests (`tests/unit/test_questions.py`, `test_f22_preflight_assist.py`, `test_b17_questions_runtime.py`, `tests/browser/test_f34_project_ui.py`, `tests/unit/test_ap5_korbat_waiting_state.py`), `docs/import-manifest.json` (1440–1454), `SPEC.md` (258–302), `AGENTS.md`, `TICKETS.md` (1457–1460).
- **Fremdangabe (Orchestrator, von mir nicht ausgeführt):** alle Testläufe (Rot-/Grünphase, `verify.sh quick`, Browser-Module, `check-*`-Skripte). Ich habe keinen Testlauf, keinen Syntaxcheck, keinen Git-Befehl ausgeführt; `shell` ist mir verweigert.
- **Nicht möglich:** `git status`/`git diff`/`git show` (kein Git-Werkzeug, `shell` → `Permission denied: shell`). Ein Diff gegen den Basisstand ist damit **nicht** belegt; Assertions-Abschwächungen gegenüber dem Basisstand und die Manifest-Hash-Aktualität sind nicht unabhängig prüfbar.

## Acceptance criteria (Ticket-Sätze und Verträge A–G)

| Kriterium | Status | Umsetzung (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Satz 1: Fragen im autonomen Modus nicht möglich | PASS | `bin/vibe_questions.py:129-131` (Wächter im Store), `bin/vibe:6614-6617` (CLI-Vorabprüfung) | `AutonomousGuardTest.test_create_refuses_without_writing_a_question` (`test_questions.py:960`), `AutonomousCliTest.test_ask_in_autonomous_mode_is_refused_without_creating_a_question` (`:1063`) — Fälle selbst gelesen (echte Assertions, keine Skips); Lauf „42 OK“ nur als Orchestrator-Fremdangabe |
| Satz 2: direkte Rückmeldung an den Agenten | PASS | `bin/vibe:6615-6616`, `bin/vibe_questions.py:48-54`, `ASK_AUTONOMOUS_HINT` `bin/vibe:6502-6503` | `test_questions.py:1084-1086` („Autonomer Modus“/„nicht möglich“, < 5 s, keine Frage-ID) — Assertions selbst gelesen |
| Satz 3: Moduswechsel erreicht den Agenten | PASS (best effort, CLI-Grenze dokumentiert) | `bin/vibe-web.py:2135-2143`, `bin/vibe:6559-6566` (Wartefreigabe) | `AutonomousNotifyApiTest.test_on_and_off_inform_the_agent_of_the_active_run` (`test_questions.py:845`, genau 2 Zustellungen nur an `ses_main`) — Assertions selbst gelesen; CLI-Grenze `docs/features/GH-58.md` (Abschnitt „Grenzen“) |
| A: zentraler Wächter im Store, nicht nur CLI | PASS | `bin/vibe_questions.py:129-131` | `test_questions.py:960-985` (keine Datei, kein Ordner) |
| B: CLI-Ablehnung sofort, Exit 0, keine Frage | PASS | `bin/vibe:6608-6617`, `6630-6634` | `test_questions.py:1063-1087` |
| C: Projektauflösung aus der Arbeitskopie | PASS | `bin/vibe:6534-6557` | `WorktreeAutonomousTest` (`test_questions.py:1279-1305`, `:1307-1324`, `:1326-1345`) |
| D: Wartefreigabe (Modus an während des Wartens) | PASS | `bin/vibe_questions.py:287-306`, `bin/vibe:6559-6566` | `test_questions.py:1089`, `:1124`, `:1170` |
| E: Wettlauf Prüfung→Frage wird autonom entschieden | PASS | `bin/vibe_packages.py:1126-1128`, `:1270` | `AutonomousRaceTest.test_create_race_hands_the_findings_to_the_agent_instead_of_unavailable` (`test_f22_preflight_assist.py:865`) — Mock simuliert nur den Wettlauf, Ergebnis wird echt geprüft (`create.call_count == 1`, keine Fragedatei) |
| F: Preflight-/Schranken-Assistenz ohne Rückfrage | PASS | `bin/vibe_packages.py:1108-1109`, `1126-1128`, `1255-1260` | `test_f22:739-833` (Bestand), Lauf „21 OK“ (Fremdangabe) |
| G: Dashboard informiert den Agenten des aktiven Laufs | PASS (best effort) | `bin/vibe-web.py:2135-2143`, `575-647` | `test_questions.py:845-874`, `:875-894` |

## Befundabgleich Runde 1

| Runde-1-Befund | Status Runde 2 | Beleg |
|---|---|---|
| **High-1** Testherkunft/Rotphase nicht belegt | **BEHOBEN (dokumentiert)** | `docs/reviews/GH-58-test-agent-report.md`: Fallliste je Klasse, Rollenmodell, Rotphase mit Befehl, `Ran 42 tests … failures=6, errors=3` und benannten Rotgründen, Grünphase, ehrliche Grenzen. Testfälle selbst gelesen und inhaltlich als echte, assertierende Fälle bestätigt. **Grenze:** Autorenschaft ist nur die Erklärung des Orchestrators (Test-Agent hatte kein `edit`/`shell`); ein unabhängiger Beleg, dass der Wortlaut vom Test-Agenten stammt, ist nicht möglich. |
| **High-2** kein Ausführungsnachweis für geänderte Unit-Module | **BEHOBEN (Fremdangabe)** | Test-Agent-Report (Unit-Module, `check-*`, `verify.sh quick`, Browser 4/17/34) und Orchestrator-Evidenz; `verify.sh full` bleibt auftragsgemäß Runner-Sache (`SPEC.md:301`, Worktree-`AGENTS.md`). |
| **Medium-3 / Doku** `docs/features/GH-58.md` fehlt, F16 falsch | **BEHOBEN mit Restbeanstandung** | `docs/features/GH-58.md` neu; `docs/features/F16.md` auf den neuen Vertrag umgestellt; `docs/features/F33.md` mit GH-58-Hinweis. Restbeanstandung: GH-58.md behauptet eine vollständige i18n-Synchronisierung (falsch, siehe Findings) und nimmt das Runde-2-Urteil vorweg. |
| **Medium-1** Wächter über `--project ""` umgehbar | **BEHOBEN** | `bin/vibe:6608-6611` (`if not project:` → Auflösung aus cwd/Registry), `6612-6613` (`ppath`-Pfad unverändert). `--project " "` (truthy) läuft in `ppath(" ")` → verständliche Ablehnung, keine Umgehung. Test: `test_questions.py:1279-1305`; der b17-Fall bleibt plausibel grün, weil `WorktreeRegistry._read` ohne Registry `[]` liefert und `_project_for_cwd` dann `None` ergibt. |
| **Medium-2** UI-Texte alte Semantik | **TEILWEISE BEHOBEN** | Behoben: `bin/web/nova-project.js:724,728`, `bin/web/app.js:235`, i18n-Schlüssel alte Fassung entfernt (grep ohne Treffer), EN-Übersetzung `i18n.js:1074`, Identitätspaar `i18n.js:1157`. Offen: fehlender `de`-Eintrag für den neuen Kartentext und unveränderte Altbeschreibung in `bin/web/app.js:413` (siehe Findings). |
| **Low-1** CLI-Umschalten ohne Push | **DOKUMENTIERT** | `docs/features/GH-58.md` („Grenzen“). |
| **Low-2** Zustellfehler verschluckt | **BEHOBEN** | `bin/vibe-web.py:2144-2155`: Protokollzeile nur bei `os.path.exists(vibe.logpath(name))`, `OSError` wird geschluckt, `msg` bleibt im Fehlerfall ohne „informiert“-Aussage (Zusatz nur bei `delivered`). |
| **Low-3** direkt geschriebene Frage-JSON | **DOKUMENTIERT** | `docs/features/GH-58.md` („Grenzen“). |

## Findings

- [Medium] `bin/web/i18n.js:1074` / `bin/web/nova-project.js:724,728` — neuer Kartentext nur englisch übersetzt; deutsche Oberfläche zeigt einen englischen Satz
  - Evidence: Der Schlüssel `"Im autonomen Modus sind Rückfragen nicht möglich; der Agent entscheidet offene Punkte selbst"` existiert ausschließlich in `DICTS.en` (`i18n.js:1074`; `DICTS.de` beginnt bei `i18n.js:1135`, ein Treffer fehlt dort, ebenso im `extend`-Block `nova-project.js:1952ff`). `t()` fällt bei fehlendem `de`-Schlüssel auf `DICTS[DEFAULT_LANG]` = `en` zurück (`i18n.js:2201-2205`), die Karte rendert über `tr(...)`. Ergebnis: In der auf Deutsch gestellten Oberfläche erscheint der zentrale neue Erklärtext auf Englisch neben deutschen Texten. `docs/features/GH-58.md` behauptet dagegen vollständige Synchronisierung, und `docs/baseline.md` dokumentiert „Wörterbücher mit vollständigen en/de-Einträgen“. Kein Test fängt das: `tests/browser/test_f34_project_ui.py` prüft `r"beantwortet|automatisch|rückfragen|questions"` case-insensitiv und ist damit in beiden Sprachen grün; die Fehlerklasse ist im Projekt sonst ausdrücklich abgesichert (`tests/unit/test_ap5_korbat_waiting_state.py:640-664`: Fehlerfall „fällt bei deutscher Oberfläche auf den englischen Default zurück“).
  - Required fix: In `DICTS.de` das Identitätspaar für den neuen Kartenschlüssel ergänzen (analog `i18n.js:1157`); danach `bin/web/i18n.js` im Import-Manifest neu erfassen und `bash scripts/verify.sh quick` sowie `tests.browser.test_f34_project_ui` erneut ausführen; die Aussage in `docs/features/GH-58.md` an den tatsächlichen Stand anpassen. Idealerweise ergänzt der Test-Agent einen Fall, der die `de`-Deckung dieses Schlüssels prüft.

- [Minor] `bin/web/app.js:413` (mit `bin/web/i18n.js:121,1245`) — klassische Autonomiekarte beschreibt weiterhin die alte Semantik
  - Evidence: Die Classic-Karte sagt: „…entscheidet der Agent ohne Antwort des Nutzers selbst und dokumentiert die Entscheidung als Antwort auf seine Rückfrage.“ Seit GH-58 entsteht im aktiven Modus gar keine Rückfrage mehr; der Satz ist nur noch für vor dem Umschalten entstandene Fragen zutreffend und verschweigt den Kern des neuen Vertrags. `docs/features/GH-58.md` nennt nur Karte/Tooltip aus `nova-project.js` und `app.js:235`.
  - Required fix: Beschreibung in `app.js:413` und beiden i18n-Fassungen auf den neuen Vertrag umstellen („Im autonomen Modus sind Rückfragen nicht möglich; offene Fragen von vor dem Umschalten beantwortet der Agent selbst und dokumentiert die Entscheidung“) oder die Abweichung ausdrücklich als Grenze dokumentieren.

- [Minor] `docs/features/GH-58.md` (Abschnitt „Nachweise“) — Dokumentation nimmt das Ergebnis dieser Reviewrunde vorweg
  - Evidence: Dort steht „… `docs/reviews/GH-58-review-2.md` (Runde 2, Verdict PASS)“. Die Datei existierte vor dieser Runde nicht, und „alle behoben“ traf zum Zeitpunkt der Formulierung nicht zu (M2 nur teilweise). Eine Nachweisdatei darf kein künftiges Prüfergebnis behaupten (`SPEC.md:267, 295`).
  - Required fix: Nach dem tatsächlichen Ergebnis formulieren und erst nach Vorliegen der Reviewdatei auf diese verweisen.

## Verification

- Change set reviewed: Arbeitsbaum `feature/m0p/gh-58` (uncommittet). **Kein Git-Diff verfügbar** (kein Git-Werkzeug; `shell` → `Permission denied: shell`); keine Vergleichsbasis in dieser Umgebung.
- Git commands run by me: keine (nicht möglich).
- Checks with supplied output (Fremdangabe, nicht von mir ausgeführt): Rotphase `test_questions` 42 Fälle, 6 failures/3 errors; `test_f22_preflight_assist` 1 error; Grünphase `test_questions` 42 OK, `test_f22_preflight_assist` 21 OK, `test_b17_questions_runtime` 6 OK, `test_b17_runner_isolation` 7 OK; `check-syntax.py`, `check-no-secrets.py`, `check-import-manifest.py` OK; `verify.sh quick` Exit 0 (auch nach M1/M2/L2); Browser `test_questions_ui` 4 OK, `test_f34_questions_ui` 17 OK, `test_f34_project_ui` 34 OK. `verify.sh full` steht aus (Runner).
- Checks not independently run: alle Build-, Unit-, Browser- und `verify.sh`-Prüfungen; Manifest-Hashes/Dateigrößen; kein Syntaxcheck.
- Important areas inspected: siehe „Prüfungsumfang“; Schwerpunkte `bin/vibe` (6500–6722), `bin/vibe_questions.py`, `bin/vibe-web.py` (Zustell-/Protokollzweig), `bin/web/{nova-project,app,i18n}.js`, `docs/features/GH-58.md`, `F16.md`, `F33.md`, beide Review-/Nachweisdateien, die betroffenen Unit- und Browser-Tests.
- Remaining risks: (1) Ohne Diff nicht belegbar, ob Assertions gegenüber dem Basisstand abgeschwächt wurden — die gelesenen GH-58-Fälle sind inhaltlich streng (Zeitgrenzen, Dateilosigkeit, Zustellanzahl, Auth). (2) `_project_for_cwd` kann bei vorhandenem Registry-Eintrag, aber fehlender Namensabbildung in `project_map()` still auf `""` zurückfallen; dokumentiert ist nur der Fall „kein Registry-Eintrag“ — in dieser Konstellation bliebe der ursprüngliche Bug bestehen (als Grenze zu dokumentieren oder durch Test abzudecken). (3) Nach jeder weiteren Änderung an `bin/web/i18n.js` muss das Manifest neu erzeugt werden (Datei ist in `docs/import-manifest.json` erfasst). (4) `TICKETS.md` GH-58 ist erwartungsgemäß noch `[ ]` ohne Commit/Test-Zeile (Abschluss nach Abnahme).

Verdict: FAIL
