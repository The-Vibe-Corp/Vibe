# Review AP17 — Runde 1

**Review result**

**AP17 „Erweiterung Agents Rollen" — Arbeitsbaum `/tmp/opencode/vibe-ap17`, Branch `feature/m0p/ap17-agent-roles` (per `.git/HEAD` verifiziert), Basiscommit `35233ff` (= origin/dev), Datum 15.11.2026. Alle Änderungen sind uncommitted (Differenz `35233ff..HEAD` laut Koordinator leer).**

## Summary
- Critical: 0
- High: 0
- Medium: 3
- Minor: 1
- Verdict: CHANGES REQUIRED

## Kontext

Ticket `TICKETS.md:1004-1010` (im produktiven Workspace, im Repo selbst aus Git ausgeschlossen): Vier Rollen `tester`, `analyst`, `sonstiges`, `content-creator` sollen explizit zuweisbar sein. SPEC.md „Agenten" (Zeilen 99-112: „Keine fest eingebauten Agentennamen für die Produktlogik. Coder und Reviewer werden über konfigurierbare Rollen zugeordnet.") und „Modellprofile" (Zeilen 138-149) verlangen keine zusätzliche Modellzuordnung je neuer Rolle; die Abgrenzung in `docs/features/AP17.md:124-129` ist korrekt.

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: Vier neue Rollen im Katalog, explizit zuweisbar, in `profiles.json` unter `rollen` gespeichert | PASS | `bin/vibe:2755` (`ROLE_NAMES`), `bin/vibe:2836-2865` (`agent_role_set`, Validierung Zeile 2841) | `tests/unit/test_ap17_agent_roles.py::RoleCatalogTest.test_role_catalog_contains_existing_and_new_roles` (Zeile 198-211: exakte Mengengleichheit, schließt extra Rollen aus), `test_all_new_roles_can_be_assigned…` (Rückgabewert + Diskstand); gelieferte Ausgabe 17 Tests OK — nicht von mir ausgeführt |
| AK2: Rollen in Agentenliste und Dashboard sichtbar/änderbar | PASS | `bin/web/app.js:1049-1053` (vier neue `option`-Einträge), Speicherpfad unverändert `/api/agent` action `role` (app.js:1055); Webservice validiert gegen denselben Katalog `bin/vibe-web.py:1669` — keine zweite Rollenliste | `tests/browser/test_ap17_agent_roles_ui.py::Ap17AgentRolesBrowserTest.test_01_…` (Zeile 257-278) und `test_02_…` (Zeile 280-305: echte Speicherung inkl. `profiles.json`-Diskprüfung); geliefert: 2 OK, `test_agents_ui` 7 OK — nicht von mir ausgeführt |
| AK3: TESTER im Preflight über Rolle `tester` auflösbar; Vorrang Argument > `project.env` > Rolle; veraltete Einträge blockieren nicht; ohne `state_dir`/ohne `profiles.json` bleibt „TESTER fehlt" | PASS | `bin/vibe_packages.py:646-663` (Fallback-Reihenfolge), `:602-614` (`agent_for_role`), `:579-599` (`role_agents`: kein `state_dir` → leer; kaputtes JSON → tolerant); Namensvalidierung `AGENT_NAME_PATTERN` Zeile 83/598 verhindert Pfad-Injectio­n über Rolleneinträge (agent_available 545-553 konkateniert den Namen in Pfade) | `TesterRolePreflightTest` (10 Fälle, Zeilen 394-583) + `TesterRoleCliTest` (2 Fälle, echte Subprozessläufe über `command_preflight`, `bin/vibe_packages.py:1296-1333`); Rotphase belegt (Bericht 263-332: alle Fallback-Fälle rot, Prioritäts-/Abgrenzungsfälle bereits grün) |
| AK4: Unbekannte Rollen abgelehnt, ohne Dateien zu verändern; Vibe-Schutzregeln unverändert | PASS | `bin/vibe:2841-2842` (ValueError vor jedem Schreiben), `:2847-2856` (letzte-Vibe-Regel, Umwidmen durch Gleichzeitigkeitszuweisung möglich) | `test_unknown_role_is_rejected_without_changing_profiles_json` (bytegleiche Vergleiche) und `test_new_roles_do_not_change_the_vibe_protection_rules`; in der Rotphase bereits grün (Bericht 173, 177-197) — Bestandsschutz-Nachweis, keine Abschwächung |
| AK5: Manifest aktualisiert und begründet | PASS mit Befund (Medium 1) | `docs/import-manifest.json:899-908` (AP17-Eintrag), `:922-924` (bin/vibe 257375/e31a988bb687…), `:982-984`, `:1022-1024` | Berichtet: `check-import-manifest.py` Exit 1 nur noch für `scripts/setup-vibe.py` (Manifest `:1182-1184`: 64185/8665fb…). Hashes von mir nicht rechenbar verifiziert (kein Shellzugriff) |
| AK6: Pflichtprüfung `bash scripts/verify.sh quick` / `full` | NOT VERIFIED | — | Nicht ausgeführt; Blockade in `docs/features/AP17.md:118-120` dokumentiert → Befund Medium 2 |
| AK7: Baseline-Abgrenzung der vorbestehenden Regressionen (2F/11E in fünf Agenten-Modulen, setup-vibe-Manifest, AP04-Pi-Hinweis) | NOT VERIFIED (nur berichtet) | `docs/features/AP17.md:105-109` | Berichtet von Coding-Agent und Koordinator (Fehlersatz am Basiscommit identisch; Ursache `ensure_test_agent`, in `35233ff` entfernt) — von mir nicht reproduzierbar (kein Git-/Shellzugriff) |
| AK8: Tests ausschließlich vom unabhängigen Test-Agenten, Rotphase vor der Implementierung | PASS | `docs/reviews/AP17-test-agent-report.md` (Herkunftserklärung Zeilen 5-13; Rotphase 147-425) | Von mir verifiziert: Alle ~12 Zeilennummern der Rotphasen-Tracebacks (Testdatei 209/226/243/292/411/433/454/472/616; Browser 276/294; Altcode `bin/vibe:2842`) stimmen exakt mit den heutigen Dateien überein — die Testdateien wurden nach der Rotphase nicht verändert. Neue Dateien, keine Vorgängerversion: keine Abschwächung möglich/erkennbar. Keine Skip-Marker, keine assertion-losen Tests, keine fang-alles-Handler |

## Findings

- [Medium] `docs/import-manifest.json:907` und `docs/features/AP17.md:115-117` — Manifest-Begründung verschweigt die vorbestehende Abweichung des Eintrags `bin/vibe`
  - Evidence: Laut Koordinator-Git-Messung (von mir nicht reproduzierbar, aber konkret beziffert) war der Manifest-Eintrag von `bin/vibe` bereits am Basiscommit `35233ff` veraltet (Manifest 263019 Bytes/`7f9982fbc228…`; tatsächlich am Basiscommit 257322 Bytes; nach AP17 257375/`e31a988bb687…`). Der AP17-Grund-Eintrag („Größe und SHA-256 der drei geänderten files-Einträge wurden aktualisiert und dadurch begründet") erklärt nur das AP17-Delta (+53 Bytes in `bin/vibe:2755`), nicht die absorbierende Korrektur der Alt-Abweichung. Die Doku-Aussage „offen bleibt ausschließlich die vorbestehende Abweichung von `scripts/setup-vibe.py`" (AP17.md:116-117) ist am Basiscommit damit falsch — auch `bin/vibe` war dort bereits abweichend. Die Projektkonvention für „Datum/Grund"-Einträge verlangt vollständige Nachvollziehbarkeit (Vorbild: REPO-AUFRÄUMEN-Eintrag `docs/import-manifest.json:896-897`, der absorbierende Übernahmen ausdrücklich benennt); `scripts/check-import-manifest.py` kennt keine Baseline-Ausnahmen, d. h. der Prüfer schlug am Basiscommit auch für `bin/vibe` an.
  - Required fix: Kein Codeeingriff. Den AP17-Grund-Eintrag ergänzen: ausdrücklich benennen, dass der Eintrag von `bin/vibe` schon am Basiscommit von der tatsächlichen Datei abwich und die Aktualisierung diese Alt-Abweichung mitlexte; die „ausschließlich"-Formulierung in `docs/features/AP17.md` entsprechend korrigieren. Zusätzlich sauber abgrenzen: `scripts/setup-vibe.py` bleibt vorbestehend abweichend (Manifest 64185/8665fb… vs. tatsächlich 70550/def52b…, laut Koordinator) und ist nicht Teil von AP17.

- [Medium] `scripts/verify.sh quick|full` — verbindliche Pflichtprüfung nicht ausgeführt
  - Evidence: AGENTS.md (Abschnitt „Prüfungen") schreibt `bash scripts/verify.sh quick` und `bash scripts/verify.sh full` nach der Implementierung verbindlich vor. `docs/features/AP17.md:118-120` dokumentiert ehrlich, dass beide im isolierten Arbeitsverzeichnis nicht ausführbar waren, weil `.vibe/project.env` dort fehlt, und dass stattdessen die Einzelbefehle liefen (Syntax, Geheimnisse, Manifest, gezielte unittest-Läufe). Die breite Regression über die gesamte Testsuite (frühere Runden lieferten z. B. 1527 bzw. 1727 Tests) fehlt dadurch; bisherige Nachweise decken nur fünf ausgewählte Regressionsmodule (122 Tests) ab. Mildernd: Die Blockade ist selbst verursacht und behebbar — der Haupt-Workspace besitzt nachweislich eine Projektumgebung (`/var/mnt/…/VibeCode/vibe/.vibe/project.env` von mir per Verzeichnislesung verifiziert), und eine minimale, unversionierte `project.env` im AP17-Arbeitsbaum wäre zulässig (`/.vibe/` ist gemäß `.gitignore:18` ausgeschlossen; produktive HOME-/VIBE-Konfigurationen dürfen dafür nicht kopiert werden, vgl. AGENTS.md „Keine produktiven HOME-/VIBE-Konfigurationen in Tests").
  - Required fix: Entweder `verify.sh quick` und `full` mit geeigneter Projektumgebung nachholen (Ergebnis inklusive der als vorbestehend belegten Fehlschläge dokumentieren) oder die Blockade präzise belegen und als ausgewiesene Abweichung in der Doku festhalten; anschließend erneute Reviewrunde.

- [Medium] `docs/reviews/AP17-test-agent-report.md:339, 362-390, 429-449` — persönliche Home-Pfade (`/home/nutzer/…`) im committeten Nachweisdokument
  - Evidence: Das Repo lehnt persönliche Home-Pfade in getrackten Inhalten ab: `scripts/build-release.py:73-82` (`HOME_PATH_RE`, Platzhalterliste enthält `nutzer`, nicht den tatsächlichen lokalen Benutzernamen) und `:199-211` (`scan_text`), angewendet über `tests/unit/test_release.py:315-347` auf alle getrackten und ungerechten Dateien. Die etablierte Praxis ist der Platzhalter: der AP7-Testbericht nutzt durchgehend `/home/nutzer/.cache/ms-playwright` (`docs/reviews/AP7-test-agent-report.md:25,181`). AP17 führt neue `/home/nutzer`-Treffer in eine neue, zu committende Nachweisdatei ein (Befehlszeile, Playwright-Tracebacks, Umgebungsabschnitt) und verstärkt damit eine bekannte, im Baseline-Fehlersatz enthaltene Regelverletzung mit paketzugehörigem Inhalt. Kein Geheimnis, aber eine persönliche Konfigurationspfad-Angabe (AGENTS.md: keine persönlichen Konfigurationen ins Repository).
  - Required fix: Vor dem Abschlusscommit die realen persönlichen Pfade im Bericht durch die Platzhalterkonvention ersetzen (z. B. `/home/nutzer/.cache/ms-playwright`, `/home/nutzer/.local/…`); der Nachweiswert bleibt erhalten, da der Befehl über die Umgebungsvariable `PLAYWRIGHT_BROWSERS_PATH` dokumentiert ist.

- [Minor] `tests/browser/test_ap17_agent_roles_ui.py:84-99` — ererbte `AGENT`-Umgebungsvariable wird nicht isoliert
  - Evidence: Das Unit-ISOLATED_ENV entfernt `AGENT` (test_ap17_agent_roles.py:70-87), das Browser-ISOLATED_ENV nicht. Die Tests setzen `AGENT` stattdessen in `project.env` (Zeile 136), ein ererbter Produktivwert bleibt aber unberührt; ich konnte keinen Codepfad finden, der `os.environ["AGENT"]` im Webservice liest (`grep` über `bin/` ohne Treffer), daher kein belegter Fehlerrisikopfad.
  - Required fix: Optional `AGENT` in die Browser-Isolationsliste aufnehmen, um Parität mit dem Unit-Test herzustellen.

## Testintegrität (geprüft, keine Verstöße)

- Keine leeren Testkörper, keine assertion-losen Tests, keine Skip-/Ignore-Marker, keine fang-alles-Handler in den neuen Testdateien (vollständig gelesen: Unit 634 Zeilen, Browser 309 Zeilen).
- Kein Mocking des zu prüfenden Verhaltens: einzig `models_list` ist auf `[]` ersetzt (Umgebungsisolierung, im Docstring begründet, test_ap17_agent_roles.py:21-22, 172-174); Preflight, `agent_role_set`, `profiles.json`, CLI-Subprozess und echtes Dashboard/Playwright sind real.
- Rotphase echt und fachlich: 6 Failures/3 Errors (Unit) bzw. 1 Failure/1 Error (Browser) mit exakt den erwarteten Ursachen (`ValueError: Unbekannte Rolle: tester/analyst`, „TESTER fehlt", fehlende Optionen); Bestandsschutzfälle waren bereits grün. Zeilenkonsistenz zwischen Rotphasenprotokoll und heutigen Dateien belegt, dass Tests nicht nachträglich verändert oder abgeschwächt wurden.

## KISS / Clean Code

- Kleinste korrekte Änderung: eine Zeile Rollenkatalog, ein Fallback-Aufruf im Preflight (analog bestehendem REVIEWER-Pfad, Wiederverwendung von `role_agents`/`agent_for_role`), vier `option`-Elemente, Manifest-Eintrag. Keine neuen Abstraktionen, keine zweite Rollenliste (Webservice nutzt denselben Katalog, `bin/vibe-web.py:1669`). Keine unrelated Refactorings erkennbar (Diffumfang laut Koordinator; die geänderten Regionen habe ich vollständig gelesen).

## Verification

- Change set reviewed: `35233ff..working tree` — **nicht als Git-Diff reproduzierbar**: Shell-/Git-Befehle wurden von den Berechtigungen verweigert (`Permission denied: shell` bei allen Versuchen). Der Changeset wurde stattdessen durch vollständige Leseprüfung des aktuellen Zustands aller fünf geänderten/neuen Dateien sowie der umgebenden Implementierung (`agent_role_set`, `agents_all`-Pfad, `vibe-web.py`-Aktion `role`, `command_preflight`, `check-import-manifest.py`, `verify.py`, `build-release.py`) rekonstruiert. Die Koordinator-Angaben zum Diff-Umfang und zur Basiscommit-Abweichung des Manifests sind gelieferte Evidenz, nicht meine Git-Messung.
- Git commands run by me: keine (Berechtigung verweigert); einzige Git-Faktenprüfung: `.git/HEAD` → `ref: refs/heads/feature/m0p/ap17-agent-roles`.
- Checks with supplied output (nicht von mir ausgeführt): Unit `tests.unit.test_ap17_agent_roles` 17 OK; Browser `test_ap17_agent_roles_ui` 2 OK, `test_agents_ui` 7 OK (PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright); Regression 122 Tests, 2F/11E am Basiscommit identisch; `check-syntax.py` OK; `check-no-secrets.py` OK; `check-import-manifest.py` Exit 1 nur für `scripts/setup-vibe.py`. Rotphase-Protokoll im Testbericht, Zeilenkonsistenz von mir verifiziert.
- Checks not independently run: alle Build-, Test-, Manifest-Hash-, verify.sh- und Git-Diff-Prüfungen.
- Important areas inspected: `bin/vibe:2745-2884`, `bin/vibe_packages.py:540-671,1296-1333`, `bin/web/app.js:1040-1064`, `bin/vibe-web.py:1660-1679`, `docs/import-manifest.json` (AP17-Eintrag + drei Dateieinträge + setup-vibe-Eintrag), `docs/features/AP17.md`, `docs/reviews/AP17-test-agent-report.md`, beide AP17-Testdateien, `scripts/verify.py`, `scripts/check-import-manifest.py`, `scripts/build-release.py:73-82,199-211`, `tests/unit/test_release.py:315-347`, TICKETS.md:1004-1010, SPEC.md:99-149, .gitignore.
- Geheimnisse/persönliche Pfade: neue Testdateien und `docs/features/AP17.md` sind sauber (keine `/home`-Treffer per grep); nur der Testbericht enthält persönliche Pfade (Befund 3).

## Baseline-Abgrenzung (Bewertung der Koordinator-Frage)

Die vorbestehenden Abweichungen sind überwiegend sauber abgegrenzt: die 2F/11E-Regression ist in `docs/features/AP17.md:105-109` mit Ursache (`ensure_test_agent`, entfernt in `35233ff`) benannt, die setup-vibe-Manifest-Abweichung in `:115-117`. Nicht sauber abgegrenzt ist die bin/vibe-Manifest-Altabweichung — sie wird still absorbiert und die „ausschließlich"-Aussage verschleiert sie (Medium 1). Die AP04-Pi-Hinweis-Abweichung ist für dieses Paket nicht relevant, da die Full-Suite nicht lief.

## Remaining risks

- Die 2F/11E-Baseline und die setup-vibe-Manifest-Abweichung sind nur berichtet, von mir nicht reproduziert.
- Manifest-Bytes/SHA-256 der drei Einträge sind nur berichtet; rechnerische Verifikation war mir technisch verwehrt.
- Trilium-Dokumentation für AP17 ist Pflicht vor dem Ticketabschluss; dazu liegen mir keine Nachweise vor (Reviewer ist read-only). Ebenso stehen Abhaken in TICKETS.md und der Abschlusscommit zurecht noch aus — erst nach finalem PASS.
- Die Modellprofile (`profilesCard`) bleiben bewusst auf Coder/Reviewer beschränkt (dokumentiert, aus SPEC gedeckt); kein Aktionsbedarf.

Verdict: CHANGES REQUIRED
