# Review AP17 — Runde 2

**Review result**

**AP17 „Erweiterung Agents Rollen" — Arbeitsbaum `/tmp/opencode/vibe-ap17`, Branch `feature/m0p/ap17-agent-roles` (per `.git/HEAD` und `.git/refs/heads/feature/m0p/ap17-agent-roles` = `35233ff733b974aacdaf06f387936bbb5b309b7e` verifiziert; damit sind alle Änderungen uncommitted gegenüber dem Basiscommit), Basiscommit `35233ff` (= origin/dev), Datum 15.11.2026.**

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

## Kontext

Ticket `TICKETS.md:1004-1010` (Dateiende, im produktiven Workspace; im Repo aus Git ausgeschlossen): Vier Rollen `tester`, `analyst`, `sonstiges`, `content-creator` sollen explizit zuweisbar sein. SPEC.md „Agenten" (`:99-112`, „Rollen frei konfigurierbar", „Keine fest eingebauten Agentennamen für die Produktlogik") und „Modellprofile" (`:138-149`, mindestens Coder und Reviewer) verlangen keine Modellzuordnung je neuer Rolle; die bewusste Abgrenzung in `docs/features/AP17.md:162-171` ist korrekt.

## Runde-1-Befunde: Fix-Prüfung

| Runde-1-Befund | Status | Evidenz |
|---|---|---|
| 1. [Medium] Manifest-Begründung/Doku verschweigt Alt-Abweichung `bin/vibe` | BEHOBEN | `docs/import-manifest.json:907` benennt ausdrücklich die Alt-Abweichung am Basiscommit (Manifest 263019 Bytes/`7f9982fbc228…`, tatsächlich 257322 Bytes) und die mitlexierende Korrektur auf 257375/`e31a988bb687…`. `docs/features/AP17.md:115-122` korrigiert die „ausschließlich"-Aussage: Offen bleibt nur noch `scripts/setup-vibe.py` (64185/8665fb… vs. 70550/def52b…), sauber als vorbestehend und nicht AP17 zugehörig abgegrenzt. Die Aussage ist jetzt wahr, weil `bin/vibe` tatsächlich korrigiert wurde |
| 2. [Medium] `verify.sh quick`/`full` nicht ausgeführt | BEHOBEN (dokumentierte Abweichung + echte Läufe) | `docs/features/AP17.md:123-160`: quick Exit 5 mit einziger Abweichung der vorbestehenden `setup-vibe.py` (2 FEHLT-Zeilen — konsistent mit `scripts/check-import-manifest.py:120-130`, das Größe und Prüfsumme getrennt meldet); full bricht an derselben vorbestehenden Manifest-Schwelle (Prüf-Exit 5 = `EXIT_CHECK`, `scripts/verify.py:48`) vor den Suiten ab. Kompensierend wurden Unit- (1812 Tests, 43F/94E) und Browser-Suite (159, 6F/1E) über die verbindliche Isolation von `scripts/verify.py` (`prepare_environment`, `:195`) gefahren und zeilenweise gegen eine Baseline-Kopie von `35233ff` (1795/41F/94E skipped=1; 157/6F/2E) abgeglichen. Die Zahlen schließen arithmetisch: 1795+17=1812 und 157+2=159 (neue AP17-Tests); Unit 41+2=43F (test_ap03-Katalog, test_release-Pfadscan) bzw. Browser 6−2 flaky+1=6F und 2−1=1E (zwei flaky Baseline-Fälle grün). Drei AP17-seitige Abweichungen sind einzeln erklärt und außer (c) mit gezielten Nachläufen (6 OK bzw. 1 OK) abgeschlossen; (c) `test_ap12` ist ein Umgebungsmangel der Prüfkopie (unversionierte `.vibe/project.env`, die das Setup seit `35233ff` nicht mehr anlegt), kein AP17-Bezug. Die Existenz der minimalen, unversionierten `.vibe/project.env` im Arbeitsbaum habe ich per Verzeichnislesung bestätigt; `/.vibe/` ist per `.gitignore:18` ausgeschlossen |
| 3. [Medium] Persönliche Home-Pfade im Testbericht | BEHOBEN | `docs/reviews/AP17-test-agent-report.md` nutzt durchgängig `/home/nutzer/…` (eigene Grep-Prüfung über die AP17-Dateien: keine Treffer persönlicher Home-Pfad-Angaben); auch `docs/reviews/AP17-review-1.md` ist maskiert. Der Nachweiswert bleibt erhalten (Befehl über `PLAYWRIGHT_BROWSERS_PATH` dokumentiert, Bericht `:475-477`) |
| 4. [Minor] Ererbtes `AGENT` im Browser-Test nicht isoliert | BEHOBEN | `tests/browser/test_ap17_agent_roles_ui.py:99` (`"AGENT"` in `ISOLATED_ENV`, Nachtrag 1 des Test-Agenten im Bericht `:487-522`, Nachläufe 2 OK und 17 OK); Parität mit dem Unit-Test (`tests/unit/test_ap17_agent_roles.py:86`) hergestellt. Es wurde keine Assertion entfernt oder abgeschwächt — der Nachtrag fügt nur einen Umgebungs Schlüssel zur Isolationsliste hinzu, was sich auch in der +1-Zeilenverschiebung der nachfolgenden Rotphasen-Zeilennummern (z. B. `select_option` jetzt `:295` statt `:294` im Rotphasenprotokoll) konsistent niederschlägt |

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: Vier neue Rollen im Katalog, explizit zuweisbar, in `profiles.json` unter `rollen` gespeichert | PASS | `bin/vibe:2755` (`ROLE_NAMES`), `bin/vibe:2836-2865` (`agent_role_set`, Validierung `:2841-2842`); Basisstand ohne neue Rollen durch Rotphase belegt (`Unbekannte Rolle: tester`, Bericht `:208`) | `tests/unit/test_ap17_agent_roles.py::RoleCatalogTest` (3 Fälle, `:198-317`: exakte Mengengleichheit schließt Extra-Rollen aus, Rückgabewert + Diskstand, `agents_all`-Sichtbarkeit); geliefert: 17 Tests OK — nicht von mir ausgeführt |
| AK2: Rollen in der Agentenliste des Dashboards sichtbar/änderbar, Auswahl wird persistiert | PASS | `bin/web/app.js:1049-1053` (vier neue `option`-Einträge), Speicherpfad unverändert `/api/agent` action `role` (`:1055`); Basisstand durch Rotphase belegt (`'tester' not found in ['', 'coder', 'reviewer', 'vibe']`, Bericht `:419`); Webservice validiert gegen denselben Katalog (`bin/vibe-web.py:1669`) — keine zweite Rollenliste | `tests/browser/test_ap17_agent_roles_ui.py::test_01_…` (`:258-279`) und `test_02_…` (`:281-306`, echte Speicherung inkl. `profiles.json`-Diskprüfung und Reload); geliefert: 2 OK — nicht von mir ausgeführt |
| AK3: TESTER im Preflight über Rolle `tester` auflösbar; Vorrang Argument > `project.env` > Rolle; veraltete Einträge blockieren nicht; ohne `state_dir`/ohne `profiles.json` bleibt „TESTER fehlt" | PASS | `bin/vibe_packages.py:646-663` (Fallback-Reihenfolge, analog REVIEWER), `:602-614` (`agent_for_role`), `:579-599` (`role_agents`: ohne `state_dir` leer, kaputtes JSON toleriert, `AGENT_NAME_PATTERN`-Filter verhindert Pfad-Injection über Rolleneinträge) | `TesterRolePreflightTest` (10 Fälle, `:394-583`) + `TesterRoleCliTest` (2 Fälle, echte Subprozessläufe `:586-630`); Rotphase `:147-332` (alle Fallback-Fälle rot, Prioritäts-/Abgrenzungsfälle bereits grün); Nachlauf 17 OK |
| AK4: Unbekannte Rollen abgelehnt, ohne Dateien zu verändern; Vibe-Schutzregeln unverändert | PASS | `bin/vibe:2841-2842` (ValueError vor jedem Schreiben), `:2847-2856` (letzte-Vibe-Regel, Umwidmen durch Gleichzeitigkeitszuweisung möglich `:2853-2856`) | `test_unknown_role_is_rejected_without_changing_profiles_json` (bytegleiche Vergleiche, `:254-276`) und `test_new_roles_do_not_change_the_vibe_protection_rules` (`:278-317`); in der Rotphase bereits grün (Bericht `:173,177-197`) — Bestandsschutz-Nachweis |
| AK5: Manifest aktualisiert und vollständig begründet (inkl. Alt-Abweichung `bin/vibe`) | PASS | `docs/import-manifest.json:899-908` (AP17-Eintrag mit Begründung `:907`), `:922-924` (bin/vibe 257375/`e31a988bb687…`), `:983`, `:1023`; `docs/` und `tests/` liegen außerhalb der Manifest-Scopes (`:1199-1207`), die neuen Dokument-/Testdateien brauchen daher keine `files`-Einträge | Gelieferte Ausgabe `verify.sh quick`: Exit 5, einzige Abweichung `setup-vibe.py` — der Prüfer (`check-import-manifest.py:120-137`) berechnet Größe/SHA selbst und hätte jede weitere Abweichung gemeldet; damit sind die drei aktualisierten Einträge indirekt belegt. Hashes von mir nicht rechenbar verifiziert (kein Shellzugriff) |
| AK6: Pflichtprüfung `bash scripts/verify.sh quick` / `full` | PASS (mit dokumentierter vorbestehender Blockade) | — | Gelieferte Läufe des Koordinators: quick Exit 5 (nur vorbestehende `setup-vibe.py`), full an derselben vorbestehenden Schwelle abgebrochen; Suiten ersatzweise unter `prepare_environment`-Isolation mit Baseline-Differenz (`docs/features/AP17.md:123-160`) — von mir nicht ausgeführt, aber die Abwägung Vollsuite-Differenz + gezielte Nachläufe statt blockiertem full-Lauf ist stimmig und verhältnismäßig |
| AK7: Tests ausschließlich vom unabhängigen Test-Agenten, Rotphase vor der Implementierung, keine Abschwächung | PASS | — | `docs/reviews/AP17-test-agent-report.md` (Herkunftserklärung `:5-13`, Rotphase `:147-425`); von mir verifiziert: Unit-Rotphasen-Zeilennummern (226, 292, 411, 472, 616) und `bin/vibe:2842` stimmen zeilengenau mit den heutigen Dateien überein; Browser-Rotphasenlinien sind um exakt +1 verschoben, was vollständig durch den dokumentierten Nachtrag 1 (eine Zeile in `ISOLATED_ENV`, `:99`) erklärbar ist — keine Abschwächung; die `test_ap03`-Katalogänderung bleibt exakte Mengengleichheit über den erweiterten Katalog (`tests/browser/test_ap03_agents_ui.py:361-378`), keine Abschwächung auf `assertIn` |
| AK8: Doku-Konsistenz (AP17.md, Testbericht, Manifest, Review-1) | PASS | `docs/features/AP17.md` (Zahlen 17/2/122, Rotphase 6F/3E bzw. 1F/1E, Suite-Vergleich) stimmt mit Testbericht und Manifest überein | Querverweise geprüft; alle im Bericht zitierten Zeilenbereiche decken sich mit den tatsächlichen Dateien |

## Findings

- [Minor] `docs/features/AP17.md:151`, `docs/reviews/AP17-review-1.md:42` — bloße Nennung des lokalen Benutzernamens in neuen Nachweisdokumenten
  - Evidence: Beide Stellen sind Beschreibungen des Runde-1-Pfad-Befunds („persönliche Home-Pfad-Angaben … maskiert" bzw. „Platzhalterliste enthält `nutzer`, nicht den tatsächlichen lokalen Benutzernamen"), keine Leaks von Autorpfaden. Die Release-Regel greift nicht (`scripts/build-release.py:73` verlangt abschließenden `/`; die gezielte Nachlaufausgabe „Ran 1 test OK" ist geliefert). Für den öffentlichen GitHub-Stand bleibt der OS-Benutzername jedoch sichtbar; Vorbildprojekt AP12 hat identische Nennungen als Minor behandelt (`docs/reviews/AP12-review-2.md:48-49`).
  - Required fix: Vor dem Abschlusscommit beide Stellen auf neutrale Formulierung umstellen (z. B. „persönliche Home-Pfad-Angaben im Review-1-Dokument"); kein Nachweiswertverlust, da der Befundinhalt unverändert dokumentiert bleibt.

## Testintegrität (geprüft, keine Verstöße)

- Keine leeren Testkörper, keine assertion-losen Tests, keine Skip-/Ignore-Marker, keine fang-alles-Handler in den AP17-Testdateien (vollständig gelesen: Unit 634 Zeilen, Browser 310 Zeilen) und in der geänderten `test_ap03_agents_ui.py` (Katalogblock `:355-389`).
- Kein Mocking des zu prüfenden Verhaltens: einzig `models_list` ist auf `[]` ersetzt (Umgebungsisolierung, Docstring `tests/unit/test_ap17_agent_roles.py:20-22`); Preflight, `agent_role_set`, `profiles.json`, CLI-Subprozess und echtes Dashboard/Playwright sind real. Browser-Test nutzt ein Ersatzprogramm für `opencode` (`:34-46`) — Infrastruktur-Ersatz, kein Testziel.
- Rotphase echt und fachlich: 6F/3E (Unit) bzw. 1F/1E (Browser) mit exakt den erwarteten Ursachen; die Basismängel sind wörtlich im Protokoll belegt (Katalogfehler `:246-250`, „TESTER fehlt" `:260,271`, fehlende Optionen `:419`).
- Beide Runde-1-Teständerungen stammen laut Bericht vom Test-Agenten (`:479-568`), sind minimal, erweitern statt schwächen ab, und die Nachläufe (17/2/6 OK) sind geliefert.
- Keine Tests verschoben oder umbenannt; `test_ap03_agents_ui.test_02` bleibt am erweiterten Katalog bestehen.

## KISS / Clean Code

- Kleinste korrekte Änderung: eine Zeile Rollenkatalog (`bin/vibe:2755`), ein symmetrischer Fallback-Aufruf im Preflight (`bin/vibe_packages.py:652-653`, Wiederverwendung von `role_agents`/`agent_for_role`), vier `option`-Elemente (`app.js:1052-1053`), ein Manifest-Eintrag. Keine neuen Abstraktionen, keine zweite Rollenliste, keine unrelated Refactorings in den gelesenen Regionen.
- Konflikte/Abgrenzung sind sauber dokumentiert (`docs/features/AP17.md:68-77,162-171`); der Webservice benötigt durch die Katalogerweiterung keine Änderung (Single Source of Truth `ROLE_NAMES`, `bin/vibe-web.py:1669` verifiziert).
- Dokumentation ist transparent über alle Abweichungen (Rotphase-Umgebung, flaky Fälle, vorbestehende Manifest-Abweichungen) informiert.

## Verification

- Change set reviewed: `35233ff..working tree` — **nicht als Git-Diff reproduzierbar**: Shell-/Git-Befehle wurden von den Berechtigungen verweigert (`Permission denied: shell` bei allen Versuchen). Der Changeset wurde stattdessen durch vollständige Leseprüfung aller geänderten/neuen Dateien rekonstruiert; der Basiszustand ist unabhängig belegt (Rotphasenprotokoll: `bin/vibe:2842`, Katalog `['', coder, reviewer, vibe]` in `app.js`, „TESTER fehlt" im Preflight) und `.git/refs/heads/feature/m0p/ap17-agent-roles` = `35233ff` bestätigt den uncommitted Stand.
- Git commands run by me: keine (Berechtigung verweigert); Git-Faktenprüfungen nur per Dateilesung: `.git/HEAD`, `.git/refs/heads/feature/m0p/ap17-agent-roles`.
- Checks with supplied output (nicht von mir ausgeführt): Unit `tests.unit.test_ap17_agent_roles` 17 OK; Browser `test_ap17_agent_roles_ui` 2 OK, `test_ap03_agents_ui` 6 OK; Regression 122 Tests 2F/11E am Basiscommit identisch; `verify.sh quick` Exit 5 (nur vorbestehende `setup-vibe.py`); full an derselben Schwelle; Vollsuite-Differenz AP17 1812 (43F/94E) / Browser 159 (6F/1E) vs. Baseline 1795 (41F/94E, skipped=1) / 157 (6F/2E); gezielte Nachläufe test_release (1 OK) und test_ap03 (6 OK). Die Zahlen habe ich arithmetisch auf Konsistenz geprüft (siehe AK6) — sie schließen.
- Checks not independently run: alle Build-, Test-, Manifest-Hash-, verify.sh-, Playwright- und Git-Diff-Prüfungen.
- Important areas inspected: `bin/vibe:2745-2884,3620-3660`, `bin/vibe_packages.py:540-671`, `bin/web/app.js:1035-1074`, `bin/vibe-web.py:1655-1684`, `docs/import-manifest.json` (AP17-Eintrag, drei `files`-Einträge, Scopes `:1199-1207`), `docs/features/AP17.md`, `docs/reviews/AP17-test-agent-report.md`, `docs/reviews/AP17-review-1.md`, beide AP17-Testdateien, `tests/browser/test_ap03_agents_ui.py`, `scripts/verify.sh`, `scripts/verify.py:1-60,380-459`, `scripts/check-import-manifest.py:1-149`, `.gitignore`, TICKETS.md:1004-1010, SPEC.md:99-149.
- Geheimnisse: keine Treffer in den AP17-Dateien; `check-no-secrets.py` OK ist geliefert.

## Restrisiken

- Alle Prüfergebnisse (Suiten, verify.sh, Hashes, Baseline-Differenz) sind Koordinator-/Testbericht-Ausgaben; ich konnte keinen davon selbst ausführen. Die arithmetische Konsistenz und die zeilengenauen Rotphasen-Tracebacks erhöhen die Verlässlichkeit, ersetzen aber keine eigene Ausführung.
- Im Arbeitsbaum liegen Laufzeitartefakte (`bin/__pycache__/*.pyc`, `vibe-storage-locks-1000/*.lock`, unversionierte `.vibe/project.env`); alle sind gitignored (`__pycache__/`, `vibe-storage-locks-*/`, `/.vibe/`), müssen aber gemäß „Projektordner sauber halten" vor dem Abschlusscommit entfernt werden — nur Paketdateien stagen.
- Trilium-Dokumentation für AP17 und Abhaken in TICKETS.md sowie der Abschlusscommit stehen noch aus (erst nach finalem PASS); dazu liegen mir keine Nachweise vor (Reviewer ist read-only).
- Die vorbestehende `setup-vibe.py`-Manifest-Abweichung und die 2F/11E-Baseline bleiben als nicht-AP17-Restbestand offen und müssen in einem eigenen Paket bereinigt werden.
- Die beiden im Minor genannten Benutzernamen-Nennungen sind reine Befundbeschreibungen; nach Umformulierung besteht kein Restrisiko für die Release-Pfadscan-Regel.

**Verdict: PASS** (0 Critical, 0 High, 0 Medium, 1 Minor — Minor-Befund vor dem Abschlusscommit beheben, ohne erneute Reviewrunde zu erzwingen, da kein Nachweiswert betroffen ist; nach AGENTS Schritt 12 gilt: keine Implementierungsänderungen ohne erneuten Review).
