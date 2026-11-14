# B13 — Review Runde 2

Datum: 14.11.2026
Reviewer: code-reviewer (unabhängig)
Stand: Arbeitsbaum auf Branch `vibe/vibe-B13-1794634424089328898-6899-666`,
Ausgangscommit `85fa466`, alles uncommitted. Folge von Runde 1
(docs/reviews/B13-review-1.md, Verdict: CHANGES REQUIRED).

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

## Acceptance criteria

Die für das Ticket maßgeblichen AK1–AK9 stammen aus dem vereinbarten Verhaltensmodell (Testbericht), das sich deckungsgleich aus dem Ticket-Fehlerbild und dem bestehenden Verhalten (SPEC/AGENTS) ableiten lässt; das Ticketszenario („Anweisung senden“ bei nicht erreichbarem Server) ist AK3 zugeordnet.

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| AK1: Privater Server je Lauf, Gesundheitsprüfung vor dem ersten Agentenaufruf, Abbruch ohne gesunden Server | PASS | `bin/vibe-run.sh:155-196` (start_private_server), `:201-219` (ensure_private_server), `:494-497` (Subshell-Aufruf), `:1063-1071` (SERVER_FAILED_FILE → Abbruch) | Runner 1–2; in `/tmp/opencode/b13-full-run2.log:588-591` beide Tests „ok“ (von mir gelesen) |
| AK2: Serverausgabe nur in `<log>.server.log`; kein Kennwort in opencode-argv, Serverdatei, Protokollen, Läuferausgabe | PASS | `bin/vibe-run.sh:81-83`, `:124-133`, `:163-166`; `assert_no_password_leak` in Tests | Runner 1, 3; run2-Log `:591-593` ok |
| AK3: Dashboard stellt an den Loopback-Endpunkt der Serverdatei zu (Hauptsession, Subagent, localhost) | PASS | `bin/vibe-web.py:445-491` (steer_server_url/steer_endpoint), `:493-527` (parametrisiertes deliver_steer), `:579-584` | Steering 1–3; run2-Log `:623-628` ok; Rotphase mit exakt dem Ticketfehlerbild im Testbericht (Kapitel „Rotphasen-Ergebnis“) belegt |
| AK4: Ohne/leerer Kennwortdatei bleibt `--standalone` bzw. verständliche Ablehnung | PASS | `bin/vibe-run.sh:42-52`, `:726-730`; `bin/vibe-web.py:582-583` | Runner 5–6, Steering 4–5 (inkl. „leer“-Variante); run2-Log `:598-601`, `:616-619` ok |
| AK5: Laufende beendet Server, entfernt Serverdatei/PID-Datei | PASS | `bin/vibe-run.sh:137-151` (stop_private_server), `:461-472` (jetzt auch ohne laufende Agentengruppe) | Runner 4 inkl. Port-Verbindungstest; run2-Log `:586-587` ok |
| AK6: Privater Server innerhalb des Sandbox-Wraps | PASS | `bin/vibe-run.sh:159-161`, `:726-729` | Runner 7 — jetzt echter Nachweis: `SANDBOX=on` im project.env (Test:621-625), exakte `state_dir(WT)/tmp`-Assertion (Test:697-701), Pflicht „Sandbox: on“ (Test:668-670); run2-Log `:594-595` ok mit echtem bwrap |
| AK7: Pi unverändert (kein privater Server, API-Ablehnung bleibt) | PASS | `bin/vibe-run.sh:726` (Harness-Gate), `:498` | Runner 8; Steering 9; run2-Log `:584-585`, `:605-606` ok |
| AK8: Defekte/fremde Serverdateien ignoriert, Rückfall | PASS | `bin/vibe-web.py:452-462`, `:474-490` | Steering 6–8 inkl. Auffangserver am „fremden“ Port; run2-Log `:610-615` ok |
| AK9: Erreichbarer gemeinsamer Server behält Ziel | PASS | `bin/vibe-run.sh:721`, `:727` | Runner 9; run2-Log `:596-597` ok |

## Findings

- [Minor] `docs/features/B13.md:178` — Fail-Zählung der Gesamtprüfung ungenau
  - Evidence: Doku und Testbericht (`docs/reviews/B13-test-agent-report.md:360`) nennen „15 Failures + 2 Errors“; beide Logs weisen tatsächlich `FAILED (failures=13, errors=2)` aus (run2-Log:2259, Baseline-Log:2212) — 15 fehlgeschlagene Tests gesamt. Die fachliche Aussage (identische Fail-Menge, leerer B13-Regressionsatz) ist unverändert richtig; ich habe die 13 FAIL-Namen und 2 ERROR-Namen beider Logs selbst abgeglichen — identisch, keine B13-Tests darunter.
  - Required fix: Bei der vor dem Commit vorgesehenen Nachweis-Verfeinerung die Zählung auf „13 Failures + 2 Errors (= 15 fehlgeschlagene Tests)“ präzisieren.
- [Minor] Trilium-Notiz `gW2aXahBDYfq` — Nachweise-Abschnitt veraltet
  - Evidence: Ich habe die Notiz über den MCP-Zugang gelesen (Existenz, Elternordner `IjRpjYJTtqam`, Labels `arbeitspaket=B13`, `projekt=vibe`, `branch`, `status=in Arbeit` verifiziert); der Schlussabsatz sagt noch „verify.sh full am finalen Stand und endgültige Commit-Referenz: folgen“, obwohl die zweite Gesamtprüfung inzwischen belegt ist. Der Koordinator hat diese Verfeinerung ausdrücklich vor dem Commit angekündigt.
  - Required fix: Im genannten Verfeinerungsschritt den Trilium-Nachweis-Abschnitt auf den neuen Stand bringen (verify-full-Ergebnis, Reviewpfad Runde 2, Commit-Referenz); ohne diesen Schritt kein Abschlusscommit.

## Bewertung der Runde-1-Umsetzung

- **Medium 1 (verify.sh full am finalen Stand):** Erbracht. `/tmp/opencode/b13-full-run2.log` (Endstand): 1753 Tests, Exit 5, `failures=13, errors=2`; `/tmp/opencode/b13-baseline-run.log` (85fa466): 1735 Tests, identische Fail-Menge — ich habe beide Fail-Mengen (13 FAIL- + 2 ERROR-Namen) selbst zeilenweise verglichen: in beide Richtungen leer. Die Differenz 1735→1753 = 18 neue B13-Tests, sämtlich grün (alle 18 „… ok“ im run2-Log:584-628 gelesen). Vorheriger Lauf `/tmp/opencode/b13-full-run.log:2257,2269` belegt die F10-Rotphase („ABBRUCH: Der private opencode-Server … nicht gesund“ bei Modus „privater opencode-Server“); in run2 kommt dieser ABBRUCH-Text nicht mehr vor (geprüft).
- **Medium 2 (Trilium):** Erbracht und von mir unabhängig lesend verifiziert (Notizinhalt deckt Fehlerbild, Umsetzung, Tests, AK, Grenzen ab). Rest: siehe Minor 2.
- **Drei Low-Befunde:** Alle drei in `docs/features/B13.md` umgesetzt — curl-argv als übernommenes Altverhalten (Zeilen 57-63), Rohmeldung bei Serverausfall (Zeilen 161-166), Port-TOCTOU (Zeilen 167-171).

## Testintegrität

- Beide B13-Suiten vollständig gelesen: keine leeren Testkörper, keine assertionsfreien Tests, keine Skip-Marker; die Assertion „status in (200, 400)“ der Ablehnungstests ist Semantik-Anpassung, keine Abschwächung (die Semantik wird zugleich über `ok:false` + Meldung + „keine Zustellung“ geprüft).
- `tests/unit/test_run_autostop.py`: Diff enthält ausschließlich Ergänzungen (REAL_CURL, deterministisch toter Port über gebundenen Socket ohne listen, `VIBE_OPENCODE_PORT`); keine Entfernung/Abschwächung. Der tote Port entfernt die Abhängigkeit vom Nutzerzustand.
- AK6-Fix: Assertion von „TMPDIR-Präfix, das zufällig vom äußeren TMPDIR stammte“ auf exakt `state_dir(WT)/tmp` desselben Sandbox-Moduls verschärft, plus Pflicht-„Sandbox: on“ — echte Verhärtung, keine Abschwächung. Rotphase der F10-Fixes durch das Full-Log belegt; die isolierte AK6-Gegenprobe (fremdes TMPDIR) ist nur im Testbericht beschrieben, aber der Endstand ist durch die verschärften Assertions und den grünen Full-Lauf mit echtem bwrap objektiv abgesichert.
- Keine Behauptung „alles getestet“: Pi-Steuerung bleibt fachlich unmöglich (F20) und ist so dokumentiert.

## Verification
- Change set reviewed: `85fa466..working tree` — von mir mit `git status --short`, `git diff --stat 85fa466` und `git diff 85fa466` pro Datei erfasst; genau 5 geänderte + 5 neue Dateien, keine weiteren (Ausschluss-Diff leer).
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git diff --stat 85fa466`, `git diff 85fa466 -- <je Datei>`, Ausschluss-Diff.
- Checks with supplied output: `verify.sh full` (B13-Stand und Baseline) — Logs von mir gelesen und Fail-Mengen selbst abgeglichen; alle 18 B13-Tests und beide F10-Tests im run2-Log als „ok“ gelesen; F10-Rotphasen-ABBRUCH im ersten Full-Log gelesen; Manifest/Syntax/Geheimnis-OK am Endstand (run2-Log Zeilen 5-7); Trilium-Notiz über MCP gelesen.
- Checks not independently run: alle Build-, Test- und Prüfskript-Aufrufe selbst (read-only-Beschränkung); `verify.sh quick` als eigenständiger Lauf (nur aus run2-Log und Dreifach-Bericht belegt); die isolierte AK6-Rotphasen-Gegenprobe.
- Important areas inspected: `bin/vibe-run.sh` (B13-Abschnitte, stop_agent_group-Refaktor, Agenten-/Reparatur-/Preflight-Pfade, AP10-Rückgabekonvention — ensure-Fehlschlag in Reparatur wird korrekt als Blockierung, nicht als „bewusstes Fortsetzen“ klassifiziert), `bin/vibe-web.py` (kompletter Steering-Pfad), beide B13-Testdateien vollständig, `runner_support.py` (Serve-Zweig, REAL_CURL), `docs/import-manifest.json`, `docs/features/B13.md`, Testbericht, Runde-1-Review, FEED.md-Status (B13 noch unchecked, korrekt).
- Remaining risks: Serverausfall mitten im Lauf liefert weiterhin die Rohtechnikmeldung (dokumentierte, akzeptierte Grenze, Folgearbeit); `::1`-Loopback-URL nicht einzeln getestet (berichtete Grenze); die 15 vorbestehenden Baseline-Fehlschläge (u. a. tmux-/TMPDIR-abhängig, `test_ap04_setup_harness`, `test_release`) sind nicht B13-bedingt und bleiben Umgebungsthemen.

**Verdict: PASS** (die beiden Minor-Befunde sind Dokupräzisierungen für den vor dem Commit vorgesehenen Verfeinerungsschritt und blockieren nicht).
