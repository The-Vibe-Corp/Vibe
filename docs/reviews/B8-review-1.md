# B8 — Unabhängiger Review, Runde 1

Datum: 2026-11-10
Reviewer: code-reviewer (unabhängig, read-only)
Gegenstand: Arbeitspaket B8 — Projekt öffnen blockiert bei nicht erreichbarem Git-Remote
Umsetzung: Commit 28cf66d (bin/vibe_github.py, bin/vibe_services.py, docs/features/B8.md)
Arbeitsstand: 8f0a47f + neue Dateien tests/unit/test_b8_no_remote_block.py (unabhängiger Test-Agent) und erweiterte docs/features/B8.md

## Summary

- Critical: 0
- High: 1
- Medium: 0
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria

Die Akzeptanzkriterien wurden vom Test-Agenten unabhängig als AC1–AC4 aus dem Ticketwortlaut abgeleitet (tests/unit/test_b8_no_remote_block.py:6–17); ich übernehme diese Gliederung.

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AC1: Projektansicht fragt Remote nie an (`remote=False`, lokale `origin/<branch>`-Referenz) | PASS (fachlich, nicht selbst ausgeführt) | `bin/vibe_services.py:125–131` (status/branches mit `remote=False`), `bin/vibe_github.py:359–365, 389–390, 434–457, 460–491` | `tests/unit/test_b8_no_remote_block.py`: `StatusLocalRefsTest` (3 Tests, echtes git, file://-Remote), `ProjectDetailLocalModeTest` (Spy-Protokoll ohne ls-remote/fetch/pull/push), `ApiProjectBlockingTest` (Ende-an-Ende über echtes `vibe-web`, hängender 127.0.0.1-Dienst, Antwort < 40 s). Grünlauf „Ran 13 tests in 12.5 s — OK, Exit 0" nur vom Koordinator mitgeliefert, von mir nicht ausgeführt |
| AC2: Ohne `GITHUB_ENABLED` generell kein Remotekontakt (auch `remote=True`) | PASS (fachlich, nicht selbst ausgeführt) | `bin/vibe_github.py:444–445` (`remote and config["enabled"]`), `469, 476` (`use_remote` / `_remote_shas` nur bei aktivierter Verknüpfung) | `NoRemoteWithoutGithubTest` (2 Tests: status/branches mit hängendem Fake, `hit_count=0`, keine Netzverben im Spy-Protokoll) |
| AC3: Fern-Leseabfragen 10 s, bewusste Aktionen 120 s | PASS (fachlich, nicht selbst ausgeführt) | `bin/vibe_github.py:45–44` (`TIMEOUT_REMOTE_READ=10`, `TIMEOUT_GIT=120`), `392–393, 404–405, 498–499` (ls-remote und Nachzieh-Fetch mit 10 s), `516, 528, 540` (fetch/pull/push mit Standard 120 s) | `RemoteReadTimeoutTest` (2 Tests: ls-remote läuft an und bricht nach ~10 s; fetch/pull/push behalten timeout=120 laut Spy) |
| AC4: Git ohne Terminal-Prompt | PASS (fachlich, nicht selbst ausgeführt) | `bin/vibe_github.py:277–278` (`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) | `PromptFreeGitTest` (3 Tests, env-Protokoll über echtes subprocess; Token nie im argv) — Restriktion mit `setdefault`, siehe Minor-Befund |
| Doku: `docs/features/B8.md` fachlich korrekt, keine erfundenen Nachweise | FAIL | `docs/features/B8.md:1–96` (Symptom/Ursache/Änderung/Grenzen: korrekt und ehrlich) | `docs/features/B8.md:98–104` behauptet Review- und Trilium-Nachweise, die nicht existieren (siehe Befund 1). Rotphasen- und Grünlauf-Angaben (Zeilen 60–81) sind plausibel und konsistent, aber nur als Agentenangabe vorhanden |

## Findings

- [High] `docs/features/B8.md:98–104` — Review- und Trilium-Nachweise behauptet, ohne dass sie existieren (erfundene Nachweise)
  - Evidence: Die Doku behauptet (a) „Review (unabhängig): `docs/reviews/B8-review-1.md` — Verdict: PASS" — diese Datei existiert nicht im Arbeitsstand (`glob docs/reviews/B8*` ohne Treffer, während alle anderen Review-Dateien vorhanden sind); der behauptete PASS ist genau diese laufende Review-Runde, die es noch nicht abgeschlossen hat. (b) „Trilium: AP8-Note im Projektvibe-Baum … Notizkennung im Ticketblock von FEEDBACK.md" — eine Trilium-Abfrage über den vorhandenen MCP-Zugang (resolve_note_id „AP8"/„B8" ohne Treffer, positive Kontrolle „AP7" → Note vDzuhFgjY4PV, Vollist der 67 Notes unter Features/„vibe") findet keine B8/AP8-Note. (c) „Ticket: FEEDBACK.md B8 mit Commit:/Test:/Review: abgehakt" — der B8-Block in FEEDBACK.md (Zeilen 413–427) ist nicht abgehakt und enthält keine Commit:/Test:/Review:-Zeilen. Damit stehen in der Doku Nachweise, die nicht vorhanden sind; AGENTS.md verbietet ausdrücklich, „keine Ergebnisse erfinden" und „keine lokale Datei als angeblich erfolgte Trilium-Dokumentation ausgeben". Der Abschnitt „Prüfungen" (B8.md:45–81) ist davon nicht betroffen und entspricht den mitgelieferten Ergebnissen.
  - Required fix: Die Ansprüche auf den tatsächlichen Stand bringen: Review-Abschnitt erst nach Abschluss dieser Review mit realer Pfadangabe und Verdict füllen (Reviewantwort nach `docs/reviews/B8-review-1.md` speichern), Trilium-Note tatsächlich über den MCP-Zugang schreiben/verifizieren und die Notizkennung erst dann nennen, und die Ticket-Abhakung erst nach Abschlusscommit vornehmen. Alternativ alle nicht existierenden Nachweisangaben bis dahin aus der Doku entfernen.

- [Minor] `bin/vibe_github.py:277–278` — `setdefault` erlaubt geerbte Umgebungsvariablen, die Prompt-Freiheit auszuhebeln
  - Evidence: `env.setdefault("GIT_TERMINAL_PROMPT", "0")` und `setdefault("GCM_INTERACTIVE", "never")` überschreiben nicht, wenn der Serverprozess bereits `GIT_TERMINAL_PROMPT=1` o. ä. erbt; der Test räumt diese Variablen vorher aus dem ENV (`test_b8_no_remote_block.py:286–289`) und deckt den Override-Fall nicht. Für die Projektansicht folgenlos (Lokalmodus ohne Netz), für Fern-Lese-/Aktionspfade kann dann dennoch ein Prompt-Versuch entstehen (bis zum 10-s- bzw. 120-s-Limit begrenzt).
  - Required fix: In der Doku/Diskussion begründen oder die Werte für Dashboard-ausgelöste Aufrufe fest setzen; andernfalls als dokumentierte Nutzerübersteuerung kennzeichnen.

- [Minor] `bin/vibe_github.py:12–13` — Modul-Docstring beschreibt das alte Verhalten der Status-Ebene
  - Evidence: Der Docstring sagt, die Git-Status-Ebene lese die Fern-Referenz „bewusst via ls-remote"; nach B8 gilt: ohne `GITHUB_ENABLED` und in der Projektansicht (`remote=False`) nie Fernkontakt. Der Docstring beschreibt nur noch den Fern-Lesemodus.
  - Required fix: Docstring-Absatz auf das neue Standardverhalten aktualisieren (lokale Referenz als Voreinstellung, ls-remote nur bei aktivierter Verknüpfung im Fern-Modus).

- [Minor] `bin/vibe_github.py:476, 494–508` — Bei gescheitertem Gesamt-ls-remote versucht `branches()` je Branch einzeln erneut (n × 10 s)
  - Evidence: Liefert `_remote_shas()` wegen Fernausfalls `{}` (unterscheidet nicht „kein origin"/„Fernfehler"), startet `_push_state` je Branch einen eigenen ls-remote mit 10 s (`bin/vibe_github.py:391–396`). Bei vielen Branchen summiert sich die Fern-Lesezeit im CLI-/Aktionskontext auf Minuten (Vor B8: dasselbe Muster mit 120 s je Aufruf — Verbesserung, aber kein Sammelfallback auf lokale Referenzen). Betrifft nicht die Projektansicht (`remote=False`).
  - Required fix: Kurze Begründung dokumentieren oder nach gescheitertem Sammelabruf auf lokale Referenzen für alle Branches ausweichen.

## Verification

- Change set reviewed: Arbeitsstand `8f0a47f` (enthält `28cf66d` B8-Commit plus nachträglich gemergte AP7/F26/F27/B7-Stände — diese sind ausdrücklich nicht Teil dieses Reviews) plus neue Dateien `tests/unit/test_b8_no_remote_block.py` und die Erweiterung `docs/features/B8.md:45–104` (ungecommittet).
- Git commands run by me: `git show --stat 28cf66d` und `git diff 28cf66d --stat` (in einem approved Aufruf); weitere Shell-/Git-Zugriffe (u. a. `git log`, `git status --short`, vollständiger Hunk-Diff von `28cf66d`) wurden von der Berechtigungsseite verweigert. Stattdessen: vollständige Lektüre der aktuellen Arbeitsdateien und der Git-Reflog-Dateien (`.git/logs/HEAD` des Haupt- und Worktree-Repositories) — daraus stammen die Commit-Kennungen 7fb9056 / 28cf66d / 8f0a47f und der Branch-Verlauf.
- Checks with supplied output: Grünlauf 13/13 OK (12,5 s), Rotphase gegen `28cf66d^` (13 FAILED/errors, 426,9 s, u. a. `/api/project`-Timeout und ls-remote ohne `GITHUB_ENABLED` mit timeout=120), Kontextsuiten test_ap06_github 54 OK / test_b7_github_auth 31 OK / test_web_api_security 22 OK, `verify.sh quick` OK, `verify.sh full` 1342 Tests mit 39+2 vorbestehenden, als B8-fremd belegten Fehlern (Gegenprobe 7fb9056) — alles nur als Agentenangabe mitgeliefert, von mir nicht unabhängig ausgeführt.
- Checks not independently run: alle Unit-/Browser-/verify-Läufe; ich habe keine Tests ausgeführt (Read-only-Review, Shell-Zugriffe ganz überwiegend verweigert).
- Important areas inspected: `bin/vibe_github.py` (voll), `bin/vibe_services.py:88–138`, `bin/vibe-web.py:680–809` (Aktionspfade `/api/github` unverändert bewusst-netzbezogen), `bin/vibe:988–1014` (CLI-Statuspfade), `bin/web/app.js` (GitHub-Karte rendert degradierte Daten ohne `error`-Behandlungsproblem), `tests/unit/test_b8_no_remote_block.py` (voll, 13 Tests: keine leeren Assertions, Spy führt echte Prozesse aus, kein echtes Netz — nur 127.0.0.1/file://), `tests/unit/test_ap06_github.py:540–599` (Bestandstests ungeschwächt, decken sogar den neuen Objekt-Nachzug), `docs/features/B8.md`, `FEEDBACK.md:400–427`, `.vibe/project.env` (TESTER=test-agent), SPEC.md/AGENTS.md.
- Remaining risks: (1) Die Behauptung, die Tests stammten unabhängig vom Test-Agenten, ist im Repo nicht beweisbar (Datei ist ungetrackt, Autor nicht prüfbar) — Koordinator muss die Zuordnung sicherstellen. (2) Die Rotphasen-/Grünlauf-Ergebnisse sind nur Agentenangaben. (3) Kein Trilium-Nachweis für B8 vorhanden (Befund 1). (4) Nicht-github-HTTPS-Fernhosts bleiben laut Doku ungetestet (dokumentiert, akzeptiert).

## Begründung

CHANGES REQUIRED: Der einzig blockierende Befund ist der High-Fund zur Nachweisintegrität in `docs/features/B8.md:98–104`: Es werden ein Review-Verdict PASS und Trilium-/Ticket-Nachweise behauptet, die zum Zeitpunkt der Doku nicht existieren (Review läuft erst jetzt; Trilium-Abfrage negativ, positive Kontrolle AP7 positiv; FEEDBACK.md-Block nicht abgehakt). Fachlich ist die Umsetzung vollständig, klein, KISS-konform (kein Caching, kein implizites Netz), die Sicherheitsregeln sind eingehalten, und die Testsuite ist inhaltlich geeignet, die Kriterien abzusichern; nach Bereinigung der Nachweisangaben (bzw. nach tatsächlichem Trilium-Eintrag und Review-Ablage) ist ein PASS ohne weitere Codeänderung möglich.
