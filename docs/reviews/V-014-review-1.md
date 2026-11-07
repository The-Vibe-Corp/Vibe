# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Kein automatisches `tools/call` | PASS | `bin/vibe_mcp.py:536-538` (nur `INIT`/`INITIALIZED`/`TOOLS_LIST` werden definiert und gesendet, 763/792/893/907/910) | `tests/unit/test_mcp_test.py:119` (lokales Methodenlog ohne `tools/call`), `tests/unit/test_mcp_test.py:343` (remote Aufzeichnung `["initialize"‚ "notifications/initialized"‚ "tools/list"]`, `assertNotIn("tools/call", ...)`) |
| Unterstützte Transporte angegeben | PASS | `bin/vibe_mcp.py:519-522,549` (`SUPPORTED_TRANSPORTS` im Ergebnis), `976-993` (unbekannter Typ + fremdes URL-Schema), `bin/vibe-web.py:1069` | `tests/unit/test_mcp_test.py:524,536` |
| OAuth-Grenzen deutlich | PASS | `bin/vibe_mcp.py:877-880` (Hinweis im Ergebnis), `941-943` (401/403-Hinweis: keine Anmeldung, Tokens nicht gelesen, `opencode mcp auth`), `bin/vibe-web.py:1069,1104` | `tests/unit/test_mcp_test.py:383` (Auth-Hinweis), `:494` (OAuth ohne Ausführung sichtbar); es wird weder Browser noch Tokenzugriff gestartet |
| Startwarnung | PASS | `bin/vibe_mcp.py:523-527` (`TEST_WARNING`), CLI `1034`, Ergebnis `warning` (544), UI `bin/vibe-web.py:1069` und Formularhinweis `1104` | `tests/unit/test_mcp_test.py:1097,1328` (`assertTrue(result["warning"])`) |
| Limits und vollständiges Prozesscleanup | PASS | `bin/vibe_mcp.py:509-517` (Konstanten), `712-732` (Stdio-Limits, drain), `559-560` (Zeitobremsung), `836-868` (HTTP/SSE-Begrenzung mit Frist), `640-646` (Diagnosegrenzen), `652-679` (`killpg` auf Prozessgruppe), `694,707` (`start_new_session`) | `tests/unit/test_mcp_test.py:154` (500 Werkzeuge begrenzt), `:254` (4-MiB stdout → Ausgabelimit), `:271` (Timeout-Kategorie), `:185` (Kindprozess exit-testet via `os.kill(pid,0)`), `:430` (Endlos-SSE <10 s) |
| Keine Geheimnisse in Ausgabe | PASS | `bin/vibe_mcp.py:586-618` (`_secret_values`: alle environment-Werte, geheime/auth-Header, URL-Parameter, `oauth.clientSecret`, token/key-Argumente), `623-646` (`_redact_*`, `_finish` über alles), `790` (serverInfo gedeckt durch `_server_info`) | `tests/unit/test_mcp_test.py:281` (stderr + serverInfo getestet, `assertNotIn` auf Ergebnis-JSON), `:383` (Header-Bearer im Fehlerpfad) |
| Ticket-Tests (Mockserver local/remote, Authfehler, Protokollfehler, Dauerstream, große Ausgabe, Kindprozess, Timeout, unbekannter Transport) | PASS | s. o. | Alle 17 Tests im vollen Log mit `ok` belegt: `/tmp/opencode/vibe-sandbox/vibe-3cdc11f549/tmp/v014-full-bwrap.log:183-199`; Gesamtergebnis `Ran 603 tests … OK` (log:622), `Ran 47 tests … OK` (log:676), `OK: Prüfung 'full' erfolgreich. (Exit 0)` (log:681) |
| Dokumentation | PASS mit Anmerkung | `docs/compatibility.md:145-192`, `docs/features/V-014.md` | „die Fehlerarten sind getrennt" (compatibility.md) wird von Kapitel nicht erfüllt (siehe Finding 1) |

Red–Green-Evidenz: Der Coding-Agent hat Umlauf-Fehlermeldungen vor der Änderung geliefert (`AttributeError: 'NoneType'` bei `result: null`, `'kaputt' != {}`, fehlender Ausgabelimit-Hinweis), die genau die drei Umlauf-Fehler testen (`tests/unit/test_mcp_test.py:218,235,472`). Plausibel und konsistent mit der Implementierung habe ich diese Fehlpfade allein via Code gelesen (vibe_mcp.py:784-788, 802-807, 911-916) bestätigt.

## Findings
- [Medium] `bin/vibe_mcp.py:794-796` — `tools/list`-Fehlschlag stets als Kategorie `protocol` (Zeitlimit-Verletzung von Abrede)
  - Evidence: Nach erfolgreichem `initialize` liefert `wait(2)` `None`, wenn das Zeitlimit abläuft (Prozess lebt noch), oder wenn der Prozess endete; beides wird pauschal mit `_fail(res, "protocol", "Keine Antwort auf 'tools/list'", …)` gemeldet (794-796). Der `initialize`-Pfad trennt dagegen korrekt: Prozess beendet → `protocol` mit Exit-Code (766-768), Prozess lebt → `timeout` (776-778). SPEC.md:177 verlangt ausdrücklich „Fehler trennen: … Timeout, … Protokoll"; `docs/compatibility.md` (neu in diesem Paket, Zeile „Die Fehlerarten sind getrennt: … `timeout` … `protocol`") behauptet diese Trennung. Häufiger Praxisfall „Handshake OK, Server hängt auf `tools/list`" wird folglich als Protokollfehler statt Zeitlimit diagnostiziert.
  - Required fix: Im `tools/list`-Zweig wie beim `initialize`-Zweig differenzieren: wenn `proc.poll() is not None` → `protocol` (mit Exit-Code in der Meldung), sonst `timeout` mit Zeitlimit-Nennung; den Truncation-Hinweis (`state["truncated"]`) in beiden Zweigen anfügen wie in 771-775. Keine neue Verzweigungslogik außerhalb `test_local`.
- [Minor] `docs/features/V-014.md:27` — Testzahl widerspricht sich im Dokument
  - Evidence: „`tests/unit/test_mcp_test.py` — 13 Tests" (Zeile 27) gegenübers, derselben Datei, „enthält 17 Tests" (Zeile 148) und 17 Tests OK. Trivialer, aber sichtbarer Dokumentationsfehler im Nachweisdokument.
  - Required fix: Zeile 27 auf „17 Tests" korrigieren; keine weitere Änderung.
- [Minor] `bin/vibe_mcp.py:884-886` / `docs/compatibility.md` — behauptetes Zeitlimit „höchstens 60/90 s" ist nicht strikt eingehalten
  - Evidence: `urlopen(timeout=wait)` begrenzt einzelne Socketoperationen (erwartbar Connect + Response-Header), die Body-Deadline wird erst danach als `time.time() + wait` gesetzt (886). Ein langsamer Server kann so das pro Anfrage Ehrenhang, annähernd 2× `wait` konsumieren, und der `initialized`-Aufruf besitzt zusätzlich ein 5-s-Wartefenster; kompatibles Worst Case liegt über der `remote`-Doku-Aussage „wartet höchstens 60 s". Begrifflich unbegrenzt ist sonst nichts.
  - Required fix: Entweder die absolute Frist vor dem Posten setzen (Deadline der Status-/Header-Phase einschließen) oder die Doku präzisieren („pro Anfrage bis zu `timeout` Wartezeit"); geeignete Stelle `docs/compatibility.md` Nur-Doku-Änderung ist für die Fallback-Variante ausreichend.
- [Minor] `bin/vibe_mcp.py:762` — nacktes positionales Kommandoargument kann unmaskiert in „Prozess gestartet: …" erscheinen
  - Evidence: `_secret_values` (586-618) sammelt `environment`, geheime `headers`/URL-Parameter, `oauth.clientSecret` sowie Argumente in den Formen `*token|key|secret|password|auth=…` bzw. `--token/--key/--secret/… <Wert>`. Ein Geheimnis als unmarkiertes positionales Argument (z. B. `["-c", server, "s3cret"]`) wird nicht erkannt, landet aber über `" ".join(cmd)` in den `steps` und damit in der Ausgabe. SPEC.md:168 verlangt „Keine Geheimnisse in … Befehlsanzeigen". Ein verlässlicher vollständiger Nachweis dienen generische Erkennung nicht möglich, somit verbleibende Restrisiken sind Grenzfälle.
  - Required fix: Dokumentierte Grenze ergänzen (in `docs/features/V-014.md` „Grenzen": nacktes positionales Geheimnis in `command` nicht maskierbar; geheime Werte über `environment`/Header oder benannte Flaggen übergeben) — alternativ ein SIGTERM gegen Abstumpf-Schreiben für unbenannte Argumente, aber keine Erzwingbarkeit behaupten.

## Verification
- Change set reviewed: `9680cb8..working tree` beschränkt auf die 7 Paketdateien; Diff 1505 Zeilen vollständig gelesen; vollständige neue Datei `tests/unit/test_mcp_test.py` (554 Zeilen) und `docs/features/V-014.md` komplett gelesen; `bin/vibe_mcp.py` (Testabschnitt 505-1002, Geheimnisschutz 280-400), `bin/vibe-web.py` (MCP-Abschnitt, Backend `/api/mcp` 506-517) im Repo gelesen.
- Git commands run by me: `git status --short`, `git log --oneline -3`, `git diff 9680cb8 --stat -- <Paketdateien>`.
- Checks with supplied output: `bash scripts/verify.sh quick` (Exit 0; Manifest 31 Dateien, Syntaxcheck, keine Geheimnisse — log:5-7), `bash scripts/verify.sh full` via `bwrap`/`env -u SANDBOX` (Exit 0; `Ran 603 tests … OK`, `Ran 47 tests … OK`, 650 erkannt — log:622-681), 17 MCP-Tests einzeln `ok` im Log (log:183-199). Fehlschläge-Evidenz (Red-Phase) als vom Coding-Agent beiforn am Umlauf, erst aus Text geliefert — gelesen, plausibel, nicht selbst aufgerufen.
- Checks not independently run: alle Build-/Testläufe, sha256-Prüfsummen des Manifests (nur über `verify.sh`-Logausgabe belegt), Trilium-Notiz `yNkNwN9tHGbU` (Inhalt nicht selbst geprüft; nur `docs/trilium-index.md`-Eintrag im Index angelegt).
- Important areas inspected: JSON-RPC-Ergebnisbehandlung (`_payload`/`_server_info`/`_tools_from`), HTTP/SSE-Reader mit Frist und Größenlimit, Prozessgruppen-Cleanup inkl. Kinder, Secret-Erfassung und -Maskierung aller Diagnosepfade (steps/error/hint/server/notes), Transport-/Konfigurations-Grundabweisung vor jedem Start, Web-UI-Bestätigungs- und CLI-Ausgabepfade, `test()`-Reihenfolge (Transport → Schema → validate).
- Remaining risks: die angeführten Grossbarkeits-/Maskierungs-Restrisiken (Finding 3 und 4); kein echter MCP-Anbieter wurde kontaktiert (Tests lokales Test-Harness), Dauerstream/Timeout-Auswirkungen nicht mit echten Servern verifiziert.

Scope: Der Diff enthält ausschließlich das Paket (keine Ferndaten; die vorbestehenden `.vibe/project.env`, `SPEC.md`, `TICKETS.md` und `docs/features/*.png` sind vom Test ausgewiesen und wurden ignoriert). Alle Toast-Ablehnungen durch die Kriterienliste und Testdateiinhalte abgeglichen; `scripts/verify.sh` wurde nicht verändert.

VERDICT: CHANGES REQUIRED
