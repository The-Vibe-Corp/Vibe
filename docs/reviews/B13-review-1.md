# B13 — Review Runde 1

Datum: 14.11.2026
Reviewer: code-reviewer (unabhängig)
Stand: Arbeitsbaum auf Branch `vibe/vibe-B13-1794634424089328898-6899-666`,
Ausgangscommit `85fa466`, alles uncommitted.
Grundlage: Diff `85fa466..Arbeitsbaum` (bin/vibe-run.sh, bin/vibe-web.py,
docs/import-manifest.json, tests/unit/runner_support.py) sowie die neuen
Dateien tests/unit/test_b13_private_server_runner.py,
tests/unit/test_b13_private_server_steering.py,
docs/reviews/B13-test-agent-report.md, docs/features/B13.md.

## Summary
- Critical: 0
- High: 0
- Medium: 2
- Minor: 3
- Verdict: CHANGES REQUIRED

## Wichtige Einschränkung der Beweismittel
Der Shell-Zugriff wurde mir verweigert (`Permission denied: shell`); ich konnte **keinerlei Git-Befehle** (`git status`, `git diff 85fa466`) selbst ausführen. Die Prüfung stützt sich daher auf (a) den gelieferten Diff `/tmp/opencode/b13-review-diff.txt` und (b) vollständige Lesezugriffe auf die Arbeitsbaumdateien, die ich an allen Schlüsselstellen (vibe-run.sh Zeilen 42–52, 78–219, 469–477, 494–497, 686–730, 883–897, 914–917, 1063–1071; vibe-web.py Zeilen 51, 445–527, 530–602) gegen den Diff abgeglichen habe — der Diff entspricht dem Arbeitsbaum. Eine unabhängige Prüfung der **Vollständigkeit** des Changesets (keine weiteren geänderten Dateien) war mir nicht möglich.

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: Privater Server je Lauf, Gesundheitsprüfung vor dem ersten Agentenaufruf, Laufabbruch ohne gesunden Server | PASS | `bin/vibe-run.sh:155-196` (start_private_server), `:201-219` (ensure_private_server), `:494-497` (Aufruf je Agentensubshell), `:1063-1071` (SERVER_FAILED_FILE → record_block, STOP) | Runner 1–2 (`test_run_starts_private_server_and_uses_it_exclusively`, `test_run_aborts_when_the_private_server_never_becomes_healthy`); Rot-/Grünphase im Testbericht belegt (gelieferte Ausgabe, nicht selbst ausgeführt) |
| AK2: Serverausgabe nur in `<log>.server.log`; Kennwort nicht in opencode-Argumenten, Serverdatei, Protokollen, Läuferausgabe | PASS | `bin/vibe-run.sh:82-83`, `:163`, `:167-178`, `:124-133` (Serverdatei ohne Kennwort) | Runner 1, 3 inkl. `assert_no_password_leak` (tests/unit/test_b13_private_server_runner.py:335-341, 464-482) |
| AK3: Dashboard stellt an den Loopback-Endpunkt der Serverdatei des aktiven Laufs zu (Hauptsession, Subagent, localhost) | PASS | `bin/vibe-web.py:445-491` (steer_server_url/steer_endpoint), `:579-584`, `:493-527` (parametrisiertes deliver_steer) | Steering 1–3; Rotphase zeigte exakt das Ticketfehlerbild „Connection refused“ (Testbericht geliefert) |
| AK4: Ohne/leerer Kennwortdatei bleibt `--standalone` bzw. verständliche Dashboard-Ablehnung | PASS | `bin/vibe-run.sh:42-52`, `:726-730`; `bin/vibe-web.py:582-583` | Runner 5–6; Steering 4–5 (inkl. „leer“-Variante) |
| AK5: Laufende beendet privaten Server und entfernt Serverdatei/PID-Datei | PASS | `bin/vibe-run.sh:137-151` (stop_private_server), `:469-477` (EXIT-Trap) | Runner 4 (`test_run_end_stops_the_private_server_and_removes_the_server_file`, Port-Verbindungstest) |
| AK6: Privater Server läuft innerhalb des Sandbox-Wraps | PASS | `bin/vibe-run.sh:159-161`, `:726-729` | Runner 7 (echtes bwrap, TMPDIR-Nachweis) |
| AK7: Pi unverändert (kein privater Server, unveränderte API-Ablehnung) | PASS | `bin/vibe-run.sh:726` (HARNESS=opencode-Gate), `:498` (Pi-Zweig) | Runner 8; Steering 9 |
| AK8: Defekte/fremde Serverdateien werden ignoriert, Rückfall auf gemeinsamen Server | PASS | `bin/vibe-web.py:452-462`, `:474-490` | Steering 6–8 (inkl. Auffangserver am „fremden“ Port) |
| AK9: Erreichbarer gemeinsamer Server behält `--server`-Ziel | PASS | `bin/vibe-run.sh:721`, `:727` | Runner 9 |

## Findings
- [Medium] `docs/features/B13.md:154` / Prozess — Verbindliche Projektprüfung `verify.sh full` nach der Implementierung nicht belegt
  - Evidence: `AGENTS.md` (Abschnitt „Prüfungen“) verlangt verbindlich `bash scripts/verify.sh quick` **und** `bash scripts/verify.sh full`. Der Testbericht weist `verify.sh full` nur am **Ausgangsstand** nach (Exit 5: 8 erwartete Rotphasenfehler + 2 vorbestehende Baseline-Mängel). Für den **fertigen Implementierungsstand** ist nur `verify.sh quick` belegt; die Nachweistabelle in `docs/features/B13.md` listet `verify.sh full` als „(folgt)“. Die definierten Regressionssuiten (76/18/57/63/14 Tests) sind selektiv und ersetzen nicht die vorgeschriebene Gesamtprüfung.
  - Required fix: `bash scripts/verify.sh full` am finalen Implementierungsstand (isoliert, `TMPDIR=/tmp`) tatsächlich ausführen und das Ergebnis inklusive der beiden bekannten vorbestehenden Baseline-Mängel und der TMPDIR-Abhängigkeit des Sandbox-Tests in `docs/features/B13.md` und Testbericht dokumentieren.
- [Medium] `docs/features/B13.md:155` / Prozess — Trilium-Dokumentation fehlt (Workflow-Schritt 7 vor Review nicht erfüllt)
  - Evidence: `AGENTS.md` Arbeitsablauf Schritt 7 verlangt die Trilium-Dokumentation **vor** dem unabhängigen Review; Definition of Done verlangt „tatsächlich durchgeführt“. Die Nachweistabelle nennt „Trilium-Dokumentation: (folgt)“; weder Bericht noch Zusammenfassung liefern einen Hinweis auf einen erfolgten, verifizierten Trilium-Schreibvorgang.
  - Required fix: B13-Dokumentation über den vorhandenen Trilium-MCP-Zugang schreiben und die Notizreferenz verifiziert nachtragen; scheitert der Zugang, BLOCKIERT melden (keine lokale Datei als Ersatz ausgeben).
- [Low] `bin/vibe-run.sh:110,182` — Kennwort erscheint als curl-Kommandozeilenargument bei den neuen privaten Gesundheitsprüfungen
  - Evidence: `curl -u "opencode:$OPENCODE_SERVER_PASSWORD"` legt das Kennwort kurzzeitig in `/proc/*/cmdline` ab. Das ist das **vorbestehende** Muster (`CURL_AUTH`, Zeile 46/57, Ausgangsstand), kein B13-Regression; die AK2-Leak-Assertions decken opencode-Argumente, Serverdatei, Protokolle und Läuferausgabe ab, nicht curl-argv (im Testbericht offen benannt). Der Kommentar in `docs/features/B13.md:46-47` („weder in der Argumentliste“) ist insoweit präzisierungsbedürftig.
  - Required fix: Restexposure in `docs/features/B13.md` ausdrücklich als übernommenes Altverhalten dokumentieren (oder als Folge-Ticket für ein argv-freies Anmeldematerial eintragen).
- [Low] `bin/vibe-web.py:524-525` — Serverausfall mitten im Lauf liefert weiterhin die Rohmeldung „[Errno 111] Connection refused“
  - Evidence: Stirbt der private Server nach der Gesundheitsprüfung, erhält der Nutzer exakt die Fehlermeldung, die das Ticket bemängelt. Als akzeptierte Grenze in `docs/features/B13.md` („Bekannte Grenzen“) benannt; das Kernproblem (`--standalone` ohne Ziel) ist behoben.
  - Required fix: Grenze in der Doku um den konkreten Rohtext ergänzen oder verständliche Fehlertexte als Folge-Ticket aufnehmen; kein Blocker für B13.
- [Low] `bin/vibe-run.sh:113-121` — Portwahl-TOCTOU bei `private_free_port`
  - Evidence: Der Port wird vor dem Serverstart freigemessen; belegt ein anderer Prozess ihn zwischenzeitlich, endet der Lauf erst nach 15 s Warten mit ABBRUCH statt mit sofortigem Neuwahl-Versuch. Verständliche Fehlermeldung vorhanden, Selbstheilung beim nächsten Lauf.
  - Required fix: Als bekannte, harmlose Race-Bedingung in der Doku vermerken; Verhalten ist korrekt abgebrochen, nicht still falsch.

## Test integrity
- Keine leeren Testkörper, keine assertionsfreien Tests, keine Skip-Marker in den beiden B13-Suiten (beide vollständig gelesen).
- Behauptete Abschwächungen: keine. Der Testbericht dokumentiert eine **Testkorrektur** (AK1-Beobachtungszeitpunkt) mit Begründung und Beweis der Unerfüllbarkeit der Alt-Erwartung; alle Inhaltsassertionen blieben erhalten (im Testbericht dargelegt; von mir nicht unabhängig verifizierbar, da kein Git-Zugriff).
- Rotphase (failing-first) ist im Testbericht mit konkret benannten Fehlern und Fehlertexten belegt; von mir nicht selbst ausgeführt.

## Verification
- Change set reviewed: `85fa466..Arbeitsbaum` — beurteilt anhand des gelieferten Diffs (`/tmp/opencode/b13-review-diff.txt`) plus vollständiger Lektüre der Neudateien; ein eigenständiger Git-Abgleich war nicht möglich.
- Git commands run by me: **keine** (Shell-Zugriff verweigert).
- Checks with supplied output: Rotphase (Exit 1, 8 erwartete Fehler), Grünphase B13-Suiten 18/18 OK, Regressionen 76/18/57/63/14 OK, `verify.sh quick` Exit 0 (60 Manifestdateien, Syntax, keine Geheimnisse) — jeweils laut Testbericht/Koordinator, nicht selbst ausgeführt.
- Checks not independently run: alle Build-, Test- und Prüfskript-Aufrufe; Git-Status/Diff.
- Important areas inspected: `bin/vibe-run.sh` (B13-Abschnitte vollständig), `bin/vibe-web.py` (Steering-Pfad vollständig), `tests/unit/test_b13_private_server_runner.py`, `tests/unit/test_b13_private_server_steering.py`, `tests/unit/runner_support.py` (Serve-Zweig), `docs/features/B13.md`, `docs/reviews/B13-test-agent-report.md`, `docs/import-manifest.json` (B13-Eintrag, `stand`).
- Remaining risks: Vollständigkeit des Changesets ohne Git nicht unabhängig bestätigt; `verify.sh full` nach Implementierung fehlt; Trilium-Status unbekannt; die 2 vorbestehenden Baseline-Mängel (`test_ap04_setup_harness`, `test_release` Home-Pfade) und der TMPDIR-abhängige Sandbox-Test sind nicht B13-bedingt und hier nicht Gegenstand.

**Verdict: CHANGES REQUIRED** (die beiden Medium-Befunde betreffen fehlende verbindliche Nachweise: `verify.sh full` am finalen Stand und die Trilium-Dokumentation; fachlich-technische Umsetzung und Testabdeckung der AK1–AK9 sind auf Basis der gelieferten Nachweise ohne Befund).
