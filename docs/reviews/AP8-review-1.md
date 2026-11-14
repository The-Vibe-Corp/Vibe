# AP8 — Review Runde 1 (code-reviewer)

Datum: 2026-11-11
Reviewer: code-reviewer (unabhängig, Subagent session ses_e381ead09ffe0PcUWEVLvzlA4D)
Gegenstand: Arbeitspaket AP8 „Bereit für Github Teil 2“, Ausgangscommit `8afde0e`, Arbeitsbaum `vibe/vibe-AP8-1794350105884804023-2529435-12489`
Antwort des Reviewers unverändert aus der Review-Antwort übernommen (siehe Hinweis am Ende).

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 3
- Info: 1
- Verdict: CHANGES REQUIRED (1 Medium-Befund; entspricht der geforderten Schlussform „Verdict: FAIL" — siehe unten)

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| `vibe_github.clone(url, target)` → (rc, Meldung) mit Cleanup, Argumentliste statt Shell, promptfrei | PASS | `bin/vibe_github.py:560-583`, `bin/vibe_github.py:271-302` | `tests/unit/test_ap8_github_checkout.py: CloneBehaviorTest` (3 Tests, inkl. Shell-Injektion `test_clone_runs_without_a_shell`), gemeldet 28/28 OK |
| Neues Projekt aus Remote im Projektordner, Name aus Parameter/URL, keine Kollision | PASS | `bin/vibe:2461-2496`, `bin/vibe:2357-2373` | `CloneAndProjectTest` (5 Tests), `ErrorCaseTest:588-618`, gemeldet OK |
| Lokale Einstellungen gewinnen: fehlende Vorlagedateien, AGENTS.md-Regelblock, Test-Agent ersetzt, project.env verwaltete Schlüssel | PASS | `bin/vibe:2499-2525`, `bin/vibe:2376-2424` (nutzt bestehende `copy_tree:2197`, `ensure_general_rules:2215`, `ensure_test_agent:2252`) | `LocalAdoptionTest` (7 Tests), gemeldet OK |
| GITHUB_REPO=owner/name + GITHUB_ENABLED=1 nur bei github.com | PASS | `bin/vibe:2489-2492`, `bin/vibe_github.py:226-261` | `test_github_com_url_sets_the_github_link_without_contacting_github:420`, `test_file_remotes_stay_without_github_keys:454` |
| Aktive Agenten auf lokal konfigurierte Agenten begrenzt, Vibe-Agent immer aktiv, Modelle gefiltert | PASS | `bin/vibe:2426-2458` | `AgentRemapTest` (3 Tests), gemeldet OK |
| CLI `vibe clone <url> [name]` | PASS | `bin/vibe:2528-2537`, Dispatcher `bin/vibe:5122` | `CommandLineTest` (3 Tests, Subprozess), gemeldet OK |
| Web `POST /api/clone {url, name?}` → `{ok, message, project}`, Tokenpflicht | PASS | `bin/vibe-web.py:764-775` (Tokenprüfung zentral `bin/vibe-web.py:691-692`) | `test_the_clone_api_creates_the_project_and_requires_the_token:375`, gemeldet 4/4 OK (echtes Dashboard, Chromium) |
| UI-Karte „Neues Projekt“ mit URL-Feld und Knopf „Aus GitHub auschecken“ | PASS | `bin/web/app.js:95-99` | `test_the_project_list_offers_the_github_checkout_card:326`, `test_an_invalid_url_reports_an_error_and_keeps_the_form_usable:435` |
| `verify.sh quick` / `full` | PASS (mit Vorbehalt) | — | Nur gemeldete Ausgabe des Koordinators: quick OK; full mit 5 verbleibenden, am Ausgangscommit 8afde0e als paketfremd dokumentierten Vorbefunden. Von mir nicht unabhängig ausführbar (keine Shell-Berechtigung). Der unabhängige Test-Agent dokumentiert denselben paketfremden Failuresatz (`docs/reviews/AP8-test-agent-report.md:351-362`). |
| Fachliche/technische Doku + Trilium | PASS | `docs/features/AP8.md` | Trilium-Notiz von mir unabhängig über MCP verifiziert: „AP8 Projekt aus GitHub auschecken (lokale Einstellungen gewinnen)" (noteId RtG0XQF3SqMN, Inhalt mit Ticket, Branch, Ausgangscommit, Prüfungen) |

## Findings
- [Medium] `bin/vibe_github.py:579` (neu, `clone()`) — Zugangsdaten in der Clone-Fehlermeldung nicht maskiert
  - Evidence: `git clone https://user:token@github.com/...` gibt bei Fehlschlag die URL inklusive eingebetteter Zugangsdaten auf stderr aus („fatal: unable to access 'https://user:token@github.com/...'"). `clone()` gibt dieses Raw-Ergebnis unverändert zurück (`return rc, _auth_guidance(out)`), und `checkout_from_github` hängt es in `bin/vibe:2485` an die ValueError-Meldung → erscheint in CLI-Fehlerausgabe und als UI-Toast via `POST /api/clone`. Das verletzt die in diesem Projekt verbindliche Regel (SPEC.md:173: „Keine Geheimnisse in Antworten, Fehlermeldungen, Befehlsanzeigen oder Logs."); das Projekt maskiert an anderen Stellen bewusst (`remotes()`, `bin/vibe_github.py:346-370`, und `mask_url` wird sogar im Namen-Fehler von `bin/vibe:2372` verwendet) — nur die neue Clone-Fehlermeldung nicht.
  - Required fix: Die Rückgabe von `clone()` (bzw. die Meldung in `checkout_from_github`) mit `vibe_github.mask_url()` behandeln, bevor sie in eine Fehlermeldung/Antwort gelangt; analog prüfen, ob die Auth-Leitfadennachricht `_auth_guidance` die Rohergebnisse enthalten darf.

- [Minor] `bin/vibe:2402-2423` (`_adopt_project_env`) — „verwaltete Schlüssel“ implizit durch Vorlageninhalt statt durch die dokumentierte Schlüsselliste definiert
  - Evidence: Doku (`docs/features/AP8.md:53-55`) und Nutzerentscheidung benennen genau TYPE, REVIEWER, TESTER, SANDBOX, SANDBOX_TOOLS, VERIFY_QUICK, VERIFY_PACKAGE, VERIFY_FULL als verwaltet. Die Implementierung überschreibt dagegen alle abweichenden Schlüssel, die in der lokalen Typlvorlage stehen. Enthält eine installierte Vorlage zusätzliche Schlüssel (z. B. VERIFY_TESTS, GITHUB_LABEL), würden mit dem Repo mitgelieferte Werte trotzdem überschrieben — die installierten Vorlagen liegen unter `PATHS.install/templates` und sind in diesem Worktree nicht einsehbar, daher nicht verifizierbar.
  - Required fix: Entweder die verwaltete Schlüsselliste als benannte Konstante implementieren und in `_adopt_project_env` verwenden, oder die Dokumentation (AP8.md) auf „alle Schlüssel der lokalen Vorlage" erweitern — Implementierung und Vertrag müssen übereinstimmen.

- [Minor] `bin/vibe:2347-2354` (`_detect_project_type`) — duplizierte Marker→Typ-Zuordnung
  - Evidence: Dieselbe Markerliste steht bereits in `ptype()` (`bin/vibe:462`). Die Duplikation ist begründbar (ptype braucht ein registriertes Projekt via `ppath()`), verletzt aber die Clean-Code-Leitlinie („keine unnötige Duplizierung"): ein künftiger neuer Marker kann an einer Stelle vergessen werden.
  - Required fix: Markerliste in eine benannte Konstante/Funktion auslagern, die beide Stellen nutzen; `ptype` behält den TYPE-Vorrang aus project.env.

- [Minor] `bin/vibe:2461-2496` (`checkout_from_github`) — Teilübernahme hinterlässt Restzustand trotz Docstring-Versprechen
  - Evidence: Docstring `bin/vibe:2465-2466`: „ein fehlgeschlagener Aufruf hinterlässt kein halbes Projekt“. Das gilt nur für den Clone-Fehler. Scheitert die Übernahme (OSError bei `copy_tree`/`_ensure_local_test_agent`, `bin/vibe:2505-2515`) oder das Speichern der GitHub-Verknüpfung (`bin/vibe:2493-2495`), bleibt das bereits eingerichtete Projektverzeichnis ohne Hinweis auf dem Zielordner zurück; ein Wiederholungsversuch scheitert mit „Zielordner existiert bereits“ ohne Löschanweisung.
  - Required fix: Entweder Zielordner bei Übernahmefehlern ebenfalls aufräumen (nur wenn vorher nicht vorhanden) oder die Fehlermeldung um den verbleibenden Pfad und die notwendige Nutzerentscheidung ergänzen und den Docstring präzisieren.

- [Info] `bin/vibe:2466-2468` — Formulierung „ohne GitHub dabei zu kontaktieren“ mehrdeutig
  - Evidence: Die Verknüpfung ruft `vibe_github.set_head_default` (`bin/vibe_github.py:676-679`, `git remote set-head origin --auto`) auf, was den Remote tatsächlich kontaktiert; gemeint ist offenbar nur, dass kein GitHub-REST-API-Aufruf und kein Token nötig ist. In Dokumentation (`docs/features/AP8.md:56-57`) präzisieren, um Fehlinterpretationen zu vermeiden.

Keine Befunde gegen die Test- oder Artefakt-Integrität: Die Tests enthalten keine leeren Prüfkörper, keine `skip`-Marker, keine nicht scheiterbaren Assertions; die Rotphase (Exit 1, `FAILED (failures=7, errors=19)` Unit / `failures=3, errors=1` Browser) ist im Test-Agentenbericht dokumentiert, und die beiden im Bericht eingeräumten vorab grünen Fehlerpfad-Tests (Red-Phase-Report „Sonderlage", Zeilen 162-170) sind implementierungsseitig real abgedeckt. `docs/import-manifest.json` wurde im selben Arbeitspaket mit Begründungseintrag AP8 aktualisiert (Diff), die Prüfskripte selbst sind nicht im Changeset. Ob das Coding-Team die Testdateien unverändert übernommen hat, ist aus Dateilektüre allein nicht beweisbar; der Bericht dokumentiert die Test-Agenten-Herkunft inklusive der beiden bereinigten Testdatei-Änderungen (Fixlauf 1/2) plausibel und konsistent mit dem Inhalt der Testdateien.

## Verification
- Change set reviewed: Ausgangscommit 8afde0e → Arbeitsbaum (Worktree vibe/vibe-AP8-17943501084804023... Branch vibe/vibe-AP8-1794350105884804023-2529435-12489), Diff über `/tmp/opencode/ap8-review-diff.patch` (414 Zeilen, 6 Dateien); Änderungen an `bin/vibe`, `bin/vibe-web.py`, `bin/vibe_github.py`, `bin/web/app.js`, `docs/baseline.md`, `docs/import-manifest.json`. Ich habe die geänderten Stellen zusätzlich direkt im Arbeitsbaum gelesen — Inhalt stimmt mit dem Diff überein.
- Git commands run by me: keine — der Shell-Zugriff wurde in dieser Review-Sitzung verweigert (permission denied auf jeden Shell-Aufruf, darunter `git status`). `git status --short` / `git diff 8afde0e` konnten daher nicht unabhängig ausgeführt werden; Vollständigkeit des Changesets stützt sich auf das bereitgestellte Diff plus direkte Gegenlesung der betroffenen Dateien und Prüfung, dass die im Diff beschriebenen Zustände (`bin/vibe:5122`, `app.js:99`, `docs/baseline.md:188/251/277`) real existieren.
- Checks with supplied output: 28/28 Unit, 4/4 Browser (echtes Dashboard, Chromium), `verify.sh quick` OK, `verify.sh full` mit 5 paketfremden Baseline-Vorbefunden, `check-import-manifest.py` OK, `test_baseline_inventory` 8/8 — alles gemeldete Ausgaben des Koordinators, von mir nicht unabhängig ausführbar. Trilium-Notiz habe ich dagegen selbst über den MCP-Zugang verifiziert (Suche + get_note, noteId RtG0XQF3SqMN).
- Checks not independently run: alle Build-, Test- und Verify-Läufe; SHA-256-Werte im Manifest; Herkunftsprüfung über Git-Metadaten (Autor der Testdateien).
- Important areas inspected: `bin/vibe:2340-2537` (AP8-Implementierung samt Helfern), `bin/vibe:2197-2276` (copy_tree/ensure_general_rules/ensure_test_agent), `bin/vibe:424-463`, `bin/vibe:880-931` (set_env_values), `bin/vibe:3270-3301` (project_agents_*), `bin/vibe_github.py:220-371, 560-583, 676-679`, `bin/vibe-web.py:685-833`, `bin/web/app.js:91-101`, beide Testdateien vollständig, `docs/features/AP8.md`, `docs/reviews/AP8-test-agent-report.md`, `docs/baseline.md`, `docs/import-manifest.json`, `SPEC.md`, `TICKETS.md`, `.vibe/project.env` (TESTER=test-agent).
- Remaining risks: Echte Netzklone gegen github.com (Auth, große Repos, Branch-Default) sind nur über die URL-Analyse/Fixtures abgedeckt und bleiben der echten Abnahme vorbehalten (vom Test-Agenten explizit als Grenze benannt); Verhalten der produktiven Toolchain-Vorlagen (TPL unter `PATHS.install/templates`) konnte ich nicht prüfen — davon hängt der Minor zu `_adopt_project_env` ab; die fünf `verify.sh full`-Baseline-Failures sind laut Bericht am Ausgangscommit identisch vorhanden, von mir nicht nachgemessen.

**Verdict: FAIL** — nicht wegen der Akzeptanzkriterien (alle fachlich mit Implementierung und Testabdeckung belegt), sondern wegen des verbleibenden Medium-Befunds (unmaskierte Zugangsdaten in der Clone-Fehlermeldung, Verstoß gegen SPEC.md:173). Nach Behebung dieses einen Punkts (und idealerweise der drei Minor-Anmerkungen) ist eine erneute Reviewrunde vorgesehen; die Arbeitspakete sind sonst reif für PASS.

---

Hinweis zur Übernahme: Diese Datei enthält die Review-Antwort des code-reviewer-Subagents wortgetreu (Struktur und Formulierungen unverändert); für diese Ablage wurden ausschließlich Überschriften, ein Kopfblok und der nachstehende Vermerk ergänzt und die Abschnittstrenner gesetzt.

Vermerk zur Bearbeitung (Koordinator): Beanstandungen werden in Review-Runde 2 behandelt; die Behobungen sind dort verzeichnet. Diese Datei bleibt als unveränderte Runde-1-Antwort bestehen.
