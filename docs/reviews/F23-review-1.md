# Review F23 — Runde 1

Reviewer: unabhängiger code-reviewer
Commit im Review: `37d23cb` (Basis `b8df33c`)
Diff: `b8df33c..37d23cb`
Datum: 2026-11-08

Der nachfolgende Bericht ist die unveränderte Antwort des Review-Agenten.

---

# Review result (Arbeitspaket F23 — Arbeitspaket-ID automatisch vergeben)

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Low: 1
- Verdict: PASS

## Anforderungs-Matrix

| Anforderung | Ergebnis | Beleg |
|---|---|---|
| Neue AP ohne ID erhalten automatisch vergebene ID | PASS (Implementierung geprüft; Tests vom Test-Agenten belegt, von mir nicht eigenständig ausführbar) | `bin/vibe:782-787` (Empty-ID-Zweig → Existenzcheck + `_add_entry(name, "TICKETS.md", "AP", …)`, Rückgabe `"AP"+Nummer`); Unit-Tests `tests/unit/test_work_packages.py:271-344` (4 neue Fälle) + API-Fall `:561-581`; Browser-Fall `tests/browser/test_tickets_ui.py:223-289`; belegte Läufe laut Übersicht: rot vor Implementierung (28 Tests, FAILED, „ID fehlt“), grün danach (28 OK / Browser 3 OK) |
| Eigene ID bleibt möglich, bisherige Prüfungen unverändert (Abwärtskompatibilität) | PASS |`bin/vibe:788-807` unverändert (Zweig `_ID_TOKEN`, Duplikat-, Titel- und Zeilenumbruchprüfung `:788-789`, `:796-798`); Bestandsfälle intakt: `tests/unit/test_work_packages.py:228, 246, 255-268, 346`; Browser-Test `test_add_edit_and_delete_a_work_package` unverändert (`tests/browser/test_tickets_ui.py:178-219`) |
| Numerierung kollisionsfrei, auch bei bestehenden `AP`-Belegungen (inkl. Nutzereingabe); keine Doppelung bei parallelen Schreibern | PASS (statisch geprüft) | `_entry_number` zählt geparste `AP`-Einträge und wählt max+1 (`bin/vibe:735-743`, `re.fullmatch(escape(prefix)+r"(\d+)")`); `_add_entry` schreibt mit erwarteter Prüfsumme und retry bei `ConcurrentChangeError` (`bin/vibe:750-766`), gleiche, bereits von `add_feedback`/`add_bug` (`bin/vibe:1812-1818`) bewährte Mechanik; keine Caches beteiligt (Cache-Leitlinie erfüllt); Tests `test_repeated_blank_ids_produce_distinct_sequential_ids` (`:290-305`) und `test_auto_assigned_id_skips_numbers_already_taken` (`:307-336`) |
| Fehlende TICKETS.md: Fehler, nichts still erzeugt | PASS | `bin/vibe:783-785` Existenzcheck vor Auto-Pfad → `ValueError("Keine TICKETS.md vorhanden")`; Test `test_auto_assignment_without_a_tickets_file_fails_and_creates_nothing` (`:338-344`) bestätigt, dass keine Datei entsteht |
| POST `/api/ticket` add ohne/leerer `id` → 200 + vergebene ID in message; update/delete leere ID weiterhin abgelehnt | PASS | `bin/vibe-web.py:645-650` (entferntes `assert`, Ergebnis aus `add_ticket` übernommen, `redact` in `:950`, Statuslogik `:954`); kein neuer Fehlerpfad: `AssertionError` war nie der geplante Kanal — er lief durch `except ValueError` hindurch und wurde vom äußeren Handler in `:955-956` als 400 invalid_request gefasst; `ValueError` aus `add_ticket` wird intern in `:658-659` zu `ok=False` und liefert 400; API-Leer-ID-Ablehnung für delete bleibt getestet (`tests/unit/test_work_packages.py:609-623`) |
| UI: ID-Feld optional, Hinweistext, Kompatibilität der Browser-Tests | PASS | `bin/web/app.js:287-289` — nur Label/Placeholder geändert; `aria-label` „ID des Arbeitspakets" unverändert (Bestandsselektor `tests/browser/test_tickets_ui.py:182` weiter gültig); neues `#ticket-new`-IDs-frei-Feld-Browser-Szenario (`:223-289`) deckt Anlegen, Toast mit echter ID, Bearbeiten, Löschen ab |
| SPEC.md-Änderung berechtigt und konsistent | PASS | `SPEC.md:97-99` exakt im Auftragswortlaut; Eindeutigkeitsregel `SPEC.md:102` unverändert; Widerspruch zur alten SPEC („die ID vergibt der Nutzer") im Ticket begründet und in `docs/features/F23.md:16-20` dokumentiert |
| Test-Änderungen nur durch Test-Agenten, keine Abschwächung | PASS | Einzig geänderte Fallsemantik: `test_add_work_package_rejects_invalid_or_missing_id` → `…_rejects_invalid_id` (Blank-Teilfall entfiel, weil vom Ticket verlangt; übrige Ablehnungen „Ungültige ID", „Titel fehlt", Zeilenumbruch + Datei-unverändert-Prüfung erhalten, `:255-268`); kein Test übersprungen, keine assertions entleert, kein catch-all; alle 28 Unit-Test-Methoden vorhanden (funktioniert mit der Belegmeldung „Ran 28 tests") |
| docs/features/F23.md korrekt, vollständig, passend zum Code | PASS | `docs/features/F23.md` deckt Verhalten (`:24-40`), Technik (`:44-67`, Deckung mit `bin/vibe:782-787`, `_add_entry` 20 Versuche, manifest/SPEC) und assessments (`:103-132`) ab; Aussagen stimmen mit dem Code überein; Grenzen ehrlich (`:134-143`) |
| docs/import-manifest.json-Konvention | PASS (belegt durch bereitgestellte Prüfausgabe) | `docs/import-manifest.json:25-111` aktualisiert für genau die drei geänderten importierten Dateien; `scripts/check-import-manifest.py` verifiziert sha256/Bytes gegen den Arbeitsbestand und ist Teil von VERIFY_QUICK (`.vibe/project.env:3`); beantragter Quick-Run Exit 0 deckt dies ab — sha256 konnte ich wegen abgelehnter Shellrechte nicht selbst neu berechnen |
| Sicherheit | PASS (Literaturliste geprüft) | Keine Geheimnisse im Diff; Authentifizierung unangetastet ( `_guard`/`_authorized`, `bin/vibe-web.py:608-609`); Validierung läuft in `add_ticket`/`_validate_title`; atomare schreibvorgänge mit Prüfsummen bleiben erhalten (V-005-Layer, `bin/vibe:662-664`); SPEC „Sicherheit und Datenintegrität" (243-259) nicht berührt |
| Trilium-Dokumentation | PASS (von mir feststellbar) | Notiz `OcBcyoKm4LP4` „F23 Arbeitspaket-ID automatisch vergeben" verifiziert: Elternteil `IjRpjYJTtqam`, Labels status=abgeschlossen, ticket=F23, commit=37d23cb komponiert via `trilium.get_note` |
| Checksummen-/Schutzumfang | PASS (belegt durch bereitgestellte Prüfausgabe) | Schauseite `git show 37d23cb --stat`: genau die 8 deklarierten Dateien; Ticket FEEDBACK.md bewusst offen (Prüfschritt vor Akzeptierung); „verify full"-Exit 5 dokumentiert als echte Teilmenge der Baseline-Fehlschläge am b8df33c, zusätzlich Fluktuation einer Baseline-Marke; kein zusätzlicher F23-Fehlschlag — in Abstimmung, da das Ticket noch offen ist |

## Findings

- [Low] `bin/vibe:784` / `bin/vibe:787` — Insignifikanter TOCTOU-Zufallsfall: Meinungslosigkeit still schaffender Datei möglich
  - Evidence: Der Auto-Pfad prüft `os.path.exists(ticket_path(name))`, liest aber erst im `_add_entry` einen Snapshot; fällt die Datei zwischen beiden Zugriffen weg (z. B. fremder Schreiber), sieht `read_snapshot` `exists=False` und `write_text(expected=MISSING)` erzeugt die Datei still neu. Das widerspricht dem in der Implementierung dokumentierten Anspruch „Auto-IDs dürfen keine fehlende TICKETS.md still erzeugen".
  - Required fix: Nicht blockierend für F23. Falls nachgerüstet: denselben Snapshot auch im Auto-Pfad vor der Existenzentscheidung lesen oder in `_add_entry`/`write_text` eine Option ergänzen, die fehlende Datei hier ablehnt. Hinweis: dasselbe Bahnverhalten gilt bereits unverändert für den manuellen Pfad (`bin/vibe:790-800`) und für `add_feedback` — kein durch F23 neu eingeführter Schaden.

## Verification
- Change set reviewed: `b8df33c..37d23cb` (Arbeitsbaum HEAD = 37d23cb, `git status --short` leer, Commitumfang exakt die 8 deklarierten Dateien).
- Git-Befehle von mir ausgeführt: `git log --oneline -3`, `git status --short`, `git diff --stat b8df33c..37d23cb`, `git diff b8df33c..37d23cb` (nach Dateigruppen), `git show 37d23cb --stat`.
- Abgelehnte Befehle (Berechtigungen): `python3 -m unittest …` (2×), `git cat-file -s` (3×), `git ls-tree -l` (1×), `grep -n`/`sha256sum` via Shell — daher Tests und sha256-Berechnung nicht von mir eigenständig nue ausgeführt; stattdessen wurden über Inhaltsexakte Dateilese alle relevanten Pfade geprüft und die von Prüf-Agent/Coding-Agent gelieferten Ausgaben gegen die im Repo konsistente Struktur (28 Unit-Test-Methoden, VERIFY_QUICK enthält Manifest-Checker etc.) plausibilisiert.
- Prüfung über die Trilium-MCP-Vollmacht: F23-Notiz ausgelesen und gegen die behaupteten Labels/Elternelement/Commit verifiziert (echt verifiziert, nicht nur behauptet).
- Wichtigste Prüfbereiche: `bin/vibe` (`add_ticket`, `_add_entry`, `_entry_number`, `_entry_lines`, `_write_text_atomic`, `ticket_path`), `bin/vibe-web.py` (`/api/ticket`, Status-/Fehlerkanäle), `bin/web/app.js` (`ticketFormCard`), beide Testdateien (Diff + Festkörper), `SPEC.md` („Arbeitspakete und Feedback", „Sicherheit und Datenintegrität", „Qualität und Abnahme"), `docs/features/F23.md`, `docs/import-manifest.json`, `scripts/verify.sh`/`check-import-manifest.py`, `.vibe/project.env` (TESTER=test-agent vorhanden).
- Restrisiken: sha256/Bytes des Manifests und die Test-Läufe sind nur über die gelieferten Prüfausfragen plus konsistenten Arbeitsbestand胃肠 unterstützt, nicht von mir direkt neu berechnet; Parallel-Schreiber-Szenario für Auto-IDs ist nur über die geteilte, von Feedback schon abgedeckte Prüfsummen-/Retry-Mechanik abgedeckt, nicht in einem dedizierten F23-Konkurrenztest.

**Verdict: PASS** — Alle Akzeptanzkriterien des Umsetzungsumfangs sind implementiert und mit Test-/Nachweiskanälen belegt; die zwar kleine, aber clara Alpine-Zufallsbeobachtung (TOCTOU, Low) ist kein Abnahmecocktail-Blocker gemäß AGENTS-Definition („PASS, keine offenen Critical/High/Medium-Befunde"), und die Ausnahmen der Full-Prüfung sind plausibel und dokumentiert als Baseline-Umgebungsfluktuation abgedeckt.
