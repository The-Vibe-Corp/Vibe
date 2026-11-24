# Review GH-58 — Runde 1 (unabhängiger Review-Agent)

Arbeitspaket: GH-58 — Autonomer Modus Einstellung wird ignoriert (GitHub #58)
Branch: feature/m0p/gh-58
Geprüfter Stand: Arbeitsbaum (uncommittet), rekonstruiert per Dateivergleich gegen den Integrationsstand /home/vibe/VibeCode/vibe
Datum: 2026-11-24
Prüfer: unabhängiger Review-Agent (Code-Review, schreib- und shell-frei; nur Lesezugriff)

## Summary

- Critical: 0
- High: 2
- Medium: 3
- Minor/Low: 3
- Verdict: FAIL

## Prüfungsumfang / Methode (nur selbst Gelesenes)

- Kein `git status`/`git diff` möglich: `shell` wurde mit `Permission denied: shell` abgewiesen; im Code-Mode-Katalog existiert kein Git-Werkzeug. Die Änderungsmenge wurde daher **nicht** per Diff, sondern durch Vergleich der Arbeitsbaum-Dateien mit dem Integrationsstand unter `/home/vibe/VibeCode/vibe/...` (gelesen, nicht verändert) rekonstruiert.
- Ermittelte Änderungsmenge (durch Dateivergleich, nicht durch Git):
  - `bin/vibe_questions.py`: neu `import vibe_autonomous` (Z. 32), `AutonomousActiveError` (Z. 44-45), `autonomous_message` (Z. 48-54), Wächter in `create` (Z. 129-131).
  - `bin/vibe`: `_project_for_cwd` (Z. 6534-6557), Vorabprüfung + Fehlerbehandlung in `cmd_ask` (Z. 6612-6615, 6628-6632), `_ask_autonomous`-Text (Z. 6529), `--runtime` in `cmd_autonomous` (Z. 6677-6678, 6692, 6698).
  - `bin/vibe_packages.py`: `except questions.AutonomousActiveError → _autonomous_result` (Z. 1126-1128).
  - `bin/vibe-web.py`: Steer bei Moduswechsel (Z. 2133-2143).
  - `bin/vibe-run.sh`: Laufhinweis (Z. 421-423, 427).
  - Tests: `tests/unit/test_questions.py` (neu: `AutonomousNotifyApiTest`, `AutonomousGuardTest`, `WorktreeAutonomousTest`, Umbau dreier CLI-Tests), `tests/unit/test_f22_preflight_assist.py` (`AutonomousRaceTest`), `docs/import-manifest.json` (Z. 1440-1451).
- Fremdangabe (vom Orchestrator, **nicht von mir ausgeführt**): `tests/browser/test_questions_ui` 4 OK, `tests/browser/test_f34_questions_ui` 17 OK mit `PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright`. Diese Module decken die GH-58-Kernverträge (zentraler Wächter, CLI-Ablehnung, Worktree-Auflösung, Dashboard-Zustellung) **nicht** ab.

## Acceptance criteria (Ticket-Sätze und Verträge A–G)

Die Vertragsbuchstaben A–G waren im mir vorliegenden Auftrag nicht ausgeschrieben; D, E und G sind in den Testdocstrings belegt (`test_questions.py:1099` „Vertrag D“, `test_f22_preflight_assist.py:878` „E“, `test_questions.py:688` „G“). A–C und F sind aus Ticket und Änderungspfaden rekonstruiert und als solche gekennzeichnet.

| Kriterium | Status | Umsetzung (file:line) | Test / Nachweis |
|---|---|---|---|
| Satz 1: Fragen im autonomen Modus nicht möglich | PASS (mit Einschränkung, siehe Befund M1) | `bin/vibe_questions.py:129-131`, `bin/vibe:6612-6615` | `AutonomousGuardTest.test_create_refuses_without_writing_a_question` (`test_questions.py:960`), `AutonomousCliTest.test_ask_in_autonomous_mode_is_refused_without_creating_a_question` (`:1063`) — **kein Laufnachweis geliefert** |
| Satz 2: direkte Rückmeldung an den Agenten | PASS | `bin/vibe:6613-6615`, `bin/vibe_questions.py:48-54` | `test_questions.py:1084-1086` (Meldung „Autonomer Modus“/„nicht möglich“, kein Warten) — kein Laufnachweis |
| Satz 3: Moduswechsel während des Laufs erreicht den Agenten | FAIL (teilweise) | `bin/vibe-web.py:2133-2143` (nur Dashboard) | `AutonomousNotifyApiTest` (`test_questions.py:845`, `:875`) — kein Laufnachweis; CLI-Pfad uninformiert (Befund L1) |
| A: zentraler Wächter im Store, nicht nur CLI | PASS | `bin/vibe_questions.py:129-131` | `test_questions.py:960-985` — kein Laufnachweis |
| B: CLI-Ablehnung sofort, Exit 0, keine Frage | PASS | `bin/vibe:6612-6615, 6628-6632` | `test_questions.py:1063-1087` — kein Laufnachweis |
| C: Projektauflösung aus der Arbeitskopie | PASS | `bin/vibe:6534-6557` | `test_questions.py:1279-1305`, `:1307-1324`, `:1326-1345` — kein Laufnachweis |
| D: Wartefreigabe (Modus an während des Wartens) | PASS | `bin/vibe_questions.py:287-306`, `bin/vibe:6559-6566` | `test_questions.py:1089`, `:1124`, `:1170` — kein Laufnachweis |
| E: Wettlauf Prüfung→Frage wird autonom entschieden | PASS | `bin/vibe_packages.py:1126-1128` | `test_f22_preflight_assist.py:865-905` — kein Laufnachweis |
| F: Preflight-/Schranken-Assistenz ohne Rückfrage | PASS | `bin/vibe_packages.py:1108-1109, 1126-1128, 1255-1260, 1293-1295` | `test_f22:739-833`, `test_ap10_gates.py:1267` (Bestand) — kein Laufnachweis |
| G: Dashboard informiert den Agenten des aktiven Laufs | PASS (best effort) | `bin/vibe-web.py:2135-2143`, `bin/vibe-web.py:575-647` | `test_questions.py:845-874` (genau 2 Zustellungen, nur `ses_main`) — kein Laufnachweis |

## Befunde

- [High] `tests/unit/test_questions.py` / `tests/unit/test_f22_preflight_assist.py` — Testherkunft und Rotphase nicht belegt
  - Evidence: Für GH-58 existiert kein Nachweis, dass die neuen Fälle (u. a. `AutonomousGuardTest`, `WorktreeAutonomousTest`, `AutonomousNotifyApiTest`, `AutonomousRaceTest`) vom Test-Agenten stammen. Die Docstrings nennen Vorbedingung/Aktion/Erwartung/Signifikanz, aber **keine** dokumentierte Rotphase (anders als `tests/unit/test_gh57_settings_backend.py:178-196` und `docs/reviews/GH-57-review-1.md:48`). `AGENTS.md` (Worktree) verlangt: „Tests werden ausschließlich vom Test-Agenten geschrieben … Ein nicht ausgeführter Test ist kein Nachweis“ und „Nur Tests, die nachweislich vom Test-Agenten stammen, zählen für die Abnahme“. Damit ist der Nachweis für alle GH-58-Kriterien derzeit nicht anerkennungsfähig.
  - Required fix: Test-Agenten-Report für GH-58 mit Fallliste und tatsächlicher Ausführung nachziehen; Rotphase (Fehlschlag vor der Implementierung, z. B. `test_create_refuses_without_creating_a_question` gegen den Basisstand) mit Befehl und Ausgabe dokumentieren — im Testdocstring oder als Nachweisdatei.

- [High] `tests/unit/test_questions.py`, `tests/unit/test_f22_preflight_assist.py`, `bin/vibe_packages.py` — kein Ausführungsnachweis für die geänderten Unit-Module
  - Evidence: Es liegt nur Browser-Fremdevidenz vor (`test_questions_ui` 4 OK, `test_f34_questions_ui` 17 OK). Für die geänderten Module `test_questions` (42 Fälle), `test_f22_preflight_assist`, `test_ap10_gates`, `test_b17_questions_runtime` wurde keine Ausgabe vorgelegt. Keines dieser Module prüft die Browser-Evidenz ab. Die Abnahme verlangt „Testprotokolle nennen Befehl, Ergebnis und Grenzen des Nachweises“ (`SPEC.md:266`).
  - Required fix: Gezielte Modulaufrufe für die betroffenen Testmodule mit Ausgabe nachreichen (Befehl + Ergebnis), zusätzlich den Nachweis der Rotphase je neuem Test; die `verify.sh`-Stufen bleiben Runner-Sache.

- [Medium] `docs/features/GH-58.md` fehlt; `docs/features/F16.md:81-84` beschreibt das alte, nun falsche Verhalten
  - Evidence: `SPEC.md:295` verlangt „`docs/features/<ID>.md` erstellen“; `SPEC.md:267` verlangt je Ticket „fachliche und technische Dokumentation“. Eine GH-58-Datei existiert nicht. F16.md sagt weiterhin: „Ist er aktiv, wird die Frage zwar gespeichert und angezeigt, aber nicht auf eine Antwort gewartet“ (Z. 81-84) — das ist durch `bin/vibe_questions.py:129-131` und `bin/vibe:6612-6615` widerlegt. Auch `vibe autonomous … --runtime` (Z. 78) und die Dashboard-Informationszustellung fehlen dort.
  - Required fix: `docs/features/GH-58.md` mit Ziel, Änderungen, Entscheidungen, Nachweisen, Grenzen anlegen und die Abschnitte „Autonomer Modus“/„CLI“ in F16.md auf den neuen Vertrag (keine Frage, direkte Rückmeldung, Zustellung beim Moduswechsel, `--runtime`) korrigieren.

- [Medium] `bin/vibe:6581-6582` / `bin/vibe_questions.py:130` — Wächter durch explizit leeres `--project` umgehbar
  - Evidence: `vibe ask --project "" "Frage"` setzt `project = ""`; `elif project:` ist falsch, es erfolgt keine Projektvalidierung, und der Wächter prüft nur die globale Voreinstellung (`is_enabled(runtime, "")`). Bei aktivem Modus für das echte Projekt entsteht dennoch eine Rückfrage (sichtbar im Dashboard), also genau das im Ticket gemeldete Verhalten über einen anderen Pfad. Der Bestandstest `tests/unit/test_b17_questions_runtime.py:216-233` nutzt diese Umgehung bewusst (Modus für „proj“ an, `--project ""`, Frage wird erwartet) und zementiert sie.
  - Required fix: Ein explizit leerer `--project`-Wert muss wie „nicht angegeben“ behandelt (Auflösung aus Arbeitsverzeichnis/Registry) oder abgelehnt werden; den b17-Testfall auf ein projektloses Szenario ohne aktiven Projektmodus umstellen (Test-Agent).

- [Medium] `bin/web/nova-project.js:724,728` und `bin/web/app.js:235` — sichtbarer Erklärungstext beschreibt weiterhin die alte Semantik
  - Evidence: Die Autonomiekarte sagt „Beantwortet offene Rückfragen automatisch, wenn keine Antwort kommt“ (i18n `bin/web/i18n.js:1074`), der Fragenknopf „Der Agent entscheidet ohne Antwort selbst …“. Nach GH-58 werden Fragen gar nicht mehr gestellt; bereits offene Fragen bleiben gemäß Vertrag D offen und werden nicht automatisch beantwortet. Die Textdateien sind nicht Teil der Änderungsmenge.
  - Required fix: Texte auf den neuen Vertrag umstellen („Im autonomen Modus sind Rückfragen nicht möglich; der Agent entscheidet selbst“) inkl. i18n-Einträge; die lockere Prüfung in `tests/browser/test_f34_project_ui.py:917-921` bleibt dadurch erfüllt.

- [Low] `bin/vibe:6698-6702` — Moduswechsel über die CLI informiert den laufenden Agenten nicht
  - Evidence: Nur `POST /api/autonomous` ruft `steer_project` (`bin/vibe-web.py:2141`); `cmd_autonomous` schreibt ausschließlich den Zustand. Ticket-Satz 3 ist damit nur für den Dashboard-Pfad umgesetzt; ein „vibe autonomous off/on“ während eines Laufs erreicht den Agenten nicht (nur ein aktiv Wartender erhält über die Wartefreigabe eine Meldung).
  - Required fix: Entweder im CLI-Pfad ebenfalls best effort zustellen oder die Einschränkung in `docs/features/GH-58.md`/F16.md ausdrücklich als Grenze dokumentieren.

- [Low] `bin/vibe-web.py:2141` — Fehlschlag der Zustellung wird verschluckt
  - Evidence: `delivered, _detail = steer_project(name, info)`; `_detail` (z. B. „Zusatzanweisungen sind bei Pi nicht möglich“, „Session nicht erfasst“, „Server nicht erreichbar“) wird verworfen. Der Nutzer erfährt nicht, dass der Agent entgegen der Ticketzusage nicht informiert wurde.
  - Required fix: Bei nicht zugestellter Information den Grund in Meldung oder Protokoll ausgeben und die Grenze dokumentieren.

- [Low] `bin/vibe_questions.py:219-242` mit `bin/vibe_sandbox.py:714-715` — direkt geschriebene Frage-JSON umgeht den Wächter
  - Evidence: `questions/` bleibt für den Agenten beschreibbar; `open_questions()` filtert nicht nach dem Modus. Ein Agent kann die Datei selbst anlegen; das Dashboard zeigt sie trotz aktivem Modus. (Gleichzeitig ist das Nicht-Filtern bewusst: Vertrag D verlangt, dass offene Fragen sichtbar bleiben.)
  - Required fix: Als bewusste Grenze dokumentieren oder die Herkunft (nur über `create`) beim Anzeigen kennzeichnen/validieren.

## Verification

- Change set reviewed: Arbeitsbaum `feature/m0p/gh-58` gegen Integrationsstand `/home/vibe/VibeCode/vibe` (Dateivergleich). **Kein Git-Diff verfügbar** (Shell gesperrt); die Änderungsmenge ist rekonstruiert, nicht git-belegt.
- Git commands run by me: keine — `git status`/`git diff` wurden mit `Permission denied: shell` abgewiesen.
- Checks with supplied output: `tests/browser/test_questions_ui` 4 OK, `tests/browser/test_f34_questions_ui` 17 OK (Fremdangabe des Orchestrators, von mir nicht nachprüfbar; `PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright`). Diese Module belegen GH-58 nicht.
- Checks not independently run: alle Build-, Unit-, Browser- und `verify.sh`-Prüfungen; kein Testlauf, kein Syntaxcheck.
- Important areas inspected: `bin/vibe_questions.py`, `bin/vibe` (6500-6705), `bin/vibe_packages.py` (980-1332, 1653-1775), `bin/vibe-web.py` (480-690, 1408-1447, 1600-1717, 2095-2144), `bin/vibe-run.sh` (419-459, 770-830, 1290-1377), `bin/vibe_sandbox.py` (600-739), `bin/web/app.js`, `bin/web/nova-project.js`, `tests/unit/test_questions.py`, `tests/unit/test_f22_preflight_assist.py`, `tests/unit/test_b17_questions_runtime.py`, `tests/unit/test_ap10_gates.py`, `tests/browser/test_questions_ui.py`, `tests/browser/test_f34_project_ui.py`, `docs/features/F16.md`, `docs/import-manifest.json`, `SPEC.md`, `AGENTS.md`, `TICKETS.md:1457`.
- Remaining risks: (1) Ohne Git-Diff ist nicht belegbar, ob Assertions gegenüber dem Basisstand abgeschwächt wurden; die drei umgebauten CLI-Tests wurden inhaltlich gleichwertig bis strenger ersetzt (Vorher/Nachher gelesen) — ohne Rotphase aber nicht anerkennungsfähig. (2) Keine Aussage zu nicht gelesenen Modulen (u. a. `bin/vibe_services.py`, übrige Browser-Sweeps). (3) `docs/import-manifest.json:1443-1447` listet die Programmdateien, aber keine Tests — konsistent mit GH-57/GH-60.

Verdict: FAIL
