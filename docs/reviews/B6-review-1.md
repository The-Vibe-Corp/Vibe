# Review-Ablage: Arbeitspaket B6 (Review Runde 1)

Grundlage: Arbeitsbaum-Diff gegen Ausgangscommit `db45bd7` (Branch
`vibe/vibe-B6-1794257245505672696-360176-25507`, Worktree `vibe-B6-KbOl3S`),
neue Testdateien des Test-Agenten (`tests/unit/test_b6_pi_events.py`,
`test_b6_harness_events_flag.py`, `test_b6_pi_runner_events.py`),
`docs/features/B6.md`, SPEC.md/AGENTS.md. Reviewer: `code-reviewer`
(Subagent, Modell GLM-5.3-Flash Free, Provider opencode), Datum 2026-11-09.
Zusätzlich vorliegende, vom Reviewer erwähnte Laufkoinzidenz: `verify.sh full`
fand zur Reviewzeit noch statt (tmpfs-Kopie); Ergebnis wird im
Abschlussnachweis ergänzt.

Nachfolgend das unveränderte Reviewergebnis des Reviewers:

---

# Review result – B6

## Header / Review-Metadaten
- Ticket: B6 (FEEDBACK.md Zeile 348) — „F24 funktioniert nicht richtig … darf nicht opencode spezifisch sein (pi harness muss funktionieren)"
- Reviewer: code-reviewer (Subagent, Modell GLM-5.3-Flash Free, Provider opencode)
- Datum: 2026-11-09
- Arbeitsbasis: Ausgangs-Commit `db45bd7`, Branch `vibe/vibe-B6-1794257245505672696-360176-25507` (Worktree `vibe-B6-KbOl3S`), alle B6-Änderungen uncommitted im Arbeitsbaum
- Reviewtyp: Runde 1 (Vor-Commit-Review), nur lesend

## Geprüfte Unterlagen
- Vollständiger Diff gegen `db45bd7` über eigene Git-Kommandos (`git diff db45bd7 --stat`, `git diff db45bd7 -- bin/vibe-run.sh bin/vibe_harness.py bin/vibe_runs.py bin/web/app.js docs/import-manifest.json`); die +203 Zeilen in `bin/vibe_runs.py` zeigen, dass `translate_pi_event`/`PI_EVENT_TYPES` an der Baseline nicht existierten — die dokumentierte Rotphase der Tests ist damit konsistent plausibel.
- Vollständige neue Testdateien `tests/unit/test_b6_pi_events.py` (742 Zeilen, 24 Tests), `tests/unit/test_b6_harness_events_flag.py` (254 Zeilen, 6 Tests), `tests/unit/test_b6_pi_runner_events.py` (452 Zeilen, 4 Tests) — keine Skip-/Ignore-Marker, keine nicht-fähigen Assertionen, keine leeren Testkörper gefunden.
- `docs/features/B6.md`, `SPEC.md` (vollständig), `AGENTS.md` des Worktrees, Tickettext in `FEEDBACK.md` (Zeilen 348–352).
- Primärquelle verifiziert: Pi-1.5.0-Dokumentation `/usr/local/lib/node_modules/@earendil-works/pi-coding-agent/docs/json.md` und das mitgelieferte Subagent-Beispielerweiterung `examples/extensions/subagent/index.ts` (Zeilen 440–499).
- Umfeld-Code ohne Diff-Änderung: `bin/vibe-web.py` (`/api/subagents`, `/api/subagent-output`, `live_subagent_output`, `subagents_of`), `bin/web/app.js` (`agentTabs`, `subagentCard`), `bin/vibe-run.sh` (`STREAM_FILTER`, Zeilen 332–335).
- Liefer.status der Prüfresultate: alle Test- und Prüfergebnisse wurden ausschließlich vom Coding-Agenten geliefert (24+6+4 OK, Regressionen OK, `node --check` OK, `verify.sh quick` Exit 0). Ich habe selbst keine Tests oder Prüfungen ausgeführt; grep der B6-Testdateien bestätigt aber strukturell keine Abweichungen. `verify.sh full` steht laut Angabe noch aus — offener Punkt. Prüfsummen in `docs/import-manifest.json` habe ich nicht unabhängig nachgerechnet (erlaubte Werkzeuge reichen nicht bis `sha256sum`).

## Akzeptanzkriterien
| Kriterium | Status | Implementierung | Test / Beleg |
|---|---|---|---|
| AK1: Pi-Ereignisse werden automatisch erkannt und als Klartext übersetzt (Session, Text, Denken, Werkzeug), kein Roh-JSON, keine Zustandsänderung bei Rauschen | PASS + Restrisiko | `bin/vibe_runs.py:104-117` (Formtabelle), `487-490` (Erkennung), `405-460` (Übersetzung), `336-402` (Werkzeuglinien) | `tests/unit/test_b6_pi_events.py` PiEventTranslationTest/PiStreamFormTest; 24 Tests OK (nur geliefert). Ereignisformen decken sich mit den von mir gelesenen Pi-docs/json.md |
| AK2: opencode-Verhalten unverändert (byte-gleiche Übersetzung, Fallback-Präfix) | PASS | `bin/vibe_runs.py:487-490` (Unterscheidung greift nur bei PI_EVENT_TYPES) | `OpencodeRegressionTest.test_stream_opencode_events_byte_identical`, `test_stream_mixed_opencode_input_keeps_behavior`; 24 Tests OK (nur geliefert) |
| AK3: Subagentenerfassung für Pi (toolCallId als Tab-Schlüssel, Statusverlauf running→completed/error, Ausgabe aus partialResult/result), UI-API unverändert | PASS + Restrisiko | `bin/vibe_runs.py:322-402`, Session-Header nie in Zustand (`bin/vibe_runs.py:422-426`) | `PiSubagentCaptureTest`, `PiSubagentApiTest` (echter Webserver, echter Filter); 24 Tests OK (nur geliefert) |
| AK4: `run_argv(..., events=True)` fügt bei Pi `--mode json` ein; ohne Flag byte-identisch; opencode nie beeinflusst | PASS | `bin/vibe_harness.py:339-341`, `448-451`, `499-504` | `test_b6_harness_events_flag.py` (6 Tests OK, nur geliefert) |
| AK5: Läufer: Pi-Zweig nutzt denselben STREAM_FILTER, Exit-Code des Agenten maßgeblich | PASS | `bin/vibe-run.sh:236-246` (Pi-Zweig mit `--json`, `PIPESTATUS[0]`), `332-335` (FILTER auch ohne Modul: `cat`) | `test_b6_pi_runner_events.py` (echter `vibe-run.sh`, 4 Tests OK, nur geliefert) |
| Gesamtkriterium: F24 funktioniert konkret mit **echtem** Pi-Harness | NOT VERIFIED | — | Kein einziger Nachweis gegen die echte `pi`-Binärdatei im Paket (siehe Befund M1) |

## Befunde nach Priorität
- Critical: keine
- High: keine
- [Medium] `bin/vibe_runs.py:104-117` / `bin/vibe-run.sh:241` — Abnahme gegen echtes Pi fehlt vollständig
  - Evidence: Die gesamte Ereigniskontrakt-Abnahme läuft über Attrappen, deren Ereignisformen der Coding-Agent (bzw. der Test-Agent) aus der Pi-Doku abgeleitet hat. Weder ein echter Aufruf `pi --print --no-session --mode json` (z. B. ohne angemeldeten Provider — nur Session-Header, Framing und Fehlerereignis, keine Modellkosten, keine OAuth) noch irgendein anderer reiner Pi-Nachweis ist im Arbeitspaket oder in `docs/features/B6.md` festgehalten. Genau das ist der Gegenstand des Tickets („wenn der pi harness benutzt wird, muss es auch funktionieren"); der gemeldete Fehler war ein echter Defekt an der echten Pi-Grenze. Bleibt der Kontrakt zur echten 1.5.0-Binärdatei ab (z. B. Header mit `--no-session`, `isError`-Feld, Skriptende mit `agent_settled`), seht der Nutzer erneut „keine der Funktionen in der UI" ohne Sichtbarkeit im Fehlerfall — kein fehlender Eintrag wäre im Fehlerbild von显现 (Pi läuft ohne Ereigniserkennung als Klartext durch) unterscheidbar.
  - Required fix: Einen echten, kostenfreien Pi-Smoke-Nachweis erbringen oder ausdrücklich dokumentieren: kurzer `pi --mode json --print --no-session`-Lauf (ohne Modell-Anmeldung eine Ereignisfolge erzeugen lassen, Befund protokollieren) oder eine begründete Blockiertmeldung in TICKETS/FEEDBACK/Doku mit dem exakten Limit. Das verreitet die Attrappen zur Doku-Quelle als belegten Kontrakt.

- [Minor] `bin/vibe_runs.py:322-333` — Pi-Subagent-Argumentschema folgt der Attrappe, nicht dem realen Pi-Subagent-Werkzeug
  - Evidence: Das mitgelieferte Pi-Beispiel `examples/extensions/subagent/index.ts` (Zeilen 457–467) definiert die Parameter `agent`, `task`, `tasks`, `chain`, `cwd`, `agentScope`, `confirmProjectAgents` — kein Feld `prompt` und kein Feld `description`. Der Pi-Eintrag erfasst deshalb an echten Pi-Läufen die Agentennamen, aber neither prompt nor Beschreibung (Tab-Label fällt auf Fallback); `docs/features/B6.md` (Grenzen) erwähnt nur mittelbar „agent/description hängt von den Werkzeugargumenten ab". Die Tests modellieren die Felder `description/lib/prompt` wie die opencode-Werkzeuge.
  - Required fix: Keine Codeanweisung der Review-Ebene: Das Grenzen-Kapitel in B6.md um das konkrete Feldschema (`task` statt `prompt`/`description`) ergänzen; falls gewünscht, im nächsten Paket eine Commons-Abgleichung über den Test-Agenten prüfen lassen.

- [Minor] `bin/vibe_runs.py:382`, `402` — Pi-`update`/`end`-Pfad meldet `changed=True`, auch ohne Zustandsdifferenz
  - Evidence: Im `update`-Zweig wird `True` bedingungslos zurückgegeben; ganze Wiederholungen identischer `partialResult`-Blöcke schreiben die Zustandsdatei erneut atomar. Korrekt, aber unnötige Schreiblast beim perpetuellen Streaming; die opencode-Übersetzung schreibt nur bei realer Differenz.
  - Required fix: Keine zwingende Änderung; falls die Abnahme das nutzt, kann der Test-Agent ergänzen assertions für gegebene Sperrsätze — ansonsten Belassung für spätere Optimierung festhalten.

- [Minor] `bin/vibe-web.py:543-550` — Rücksprung `live_subagent_output` für Pi-Einträge geht an den opencode-Server
  - Evidence: Fehlt der erfasste Ausgabetext (Pi-Subagent fehlerhaft/ohne Textblock), fragt `/api/subagent-output` den opencode-Server mit der Pi-`toolCallId` als Session-ID. Die Antwort ist leer/harmlos, aber sie ist die einzige Stelle, an der eine Pi-Kennung an den opencode-Server geraten kann — die eigentliche Aussage in B6.md „die opencode-Live-Abfrage dürfte niemals mit dieser Kennung befragt werden" wird nur über `state["session"]` gesichert, nicht über diesen Vorfallback (unveränderter Altcode).
  - Required fix: Dokumentierten Zusatz-Hinweis nachziehen oder im Folge-Ticket die Rückfrage für Einträge ohne echte Session (ohne `ses_`-Kennung) aussetzen lassen.

- [Minor] `docs/features/B6.md` (ganze Datei) — akzeptanzbeschreibung AK1–AK5 steht nicht explizit im Dokument
  - Evidence: Die von Tests und Review-Mandat genutzten AK-Nummern AK1–AK5 existieren nur in den Test-Datei-Dokumentstring; B6.md beschreibt Befund/Lösung/Grenzen/Tests ohne benannte Akzeptanzkriterien. Das erschwert die akzeptanzsprechende Nachweisführung im Ticketabschluss.
  - Required fix: B6.md um den Abschnitt „Akzeptanz" mit AK1–AK5 (wie in anderen Feature-Dokus üblich) ergänzen — reine Dokumentation, kein Code.

## Verifikation
- Change set reviewed: `db45bd7..working tree` (eigene Git-Kommandos: `git status --short`, `git diff --stat db45bd7`, `git diff db45bd7 -- <Dateien>`, `git log --oneline -6`); neue Dateien vollständig gelesen.
- Git commands run by me: `git status --short`, `git diff db45bd7 --stat/--shortstat`, `git diff db45bd7 -- bin/vibe-run.sh bin/web/app.js bin/vibe_harness.py bin/vibe_runs.py docs/import-manifest.json`, `git log --oneline -6`.
- Checks with supplied output (nur vom Coding-Agenten geliefert, von mir keine Ausführung): `python3 -m unittest` der drei B6-Dateien (24/6/4 OK), Regressionssuiten (F24, F19-API/Läufer, AP04, F25, F20, Browser f20, F27), `node --check bin/web/app.js`, `bash scripts/verify.sh quick` (Exit 0), Rotphasenprotokoll (34 Tests, failures=6, errors=17).
- Checks not independently run: alle Build-/Test-Kommandos; kein `verify.sh full`-Ergebnis vorhanden (läuft laut Angabe noch) — kein Befund hier, solange das Ergebnis beim Ticketabschluss benannt ist; Prüfsummenmanuell unverifikat (`sha256sum` nicht in meinen Rechten).
- Strukturelle Prüfungen von mir: git-grep der B6-Tests auf skip/ignore/assume (keine Treffer), Abgleich der Ereignisformen gegen die lokale Pi-1.5.0-Doku (Deckung mit `PI_EVENT_TYPES`, `toolCallId/toolName/args/partialResult/result/isError`, Session-Header `id`), Prüfung des UI-Auswertepfads (`app.js agentTabs`: Label-Fallback `agent` → „Subagent", Anzeige nur bei `status==='running'`).
- Remaining risks: echtes Pi-Kontraktverhalten (Befund M1); `import-manifest.json`-Prüfsummen nicht independent bestätigt; Trilium-Dokumentation im Mandat erwartbar aber hier nicht nachgewiesen (AGENTS-Vorgabe „Diese Dokumentation zusätzlich über den vorhandenen Trilium-MCP-Zugang dokumentieren") — Ticket darf erst mit tatsächlichem Nachweis abgehakt werden; Befehlsvarianten in `vibe-run.sh` mit leerem `wrap`/`STREAM_FILTER`=cat sind getestet („kein stiller Abbruch" via `cat`-Fallback), aber die Pi-Kombination Sandbox+JSON-Modus hat nur Attrappenabdeckung.

**Verdict: CHANGES REQUIRED**
