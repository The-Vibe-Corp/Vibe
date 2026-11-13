# B12 — Test-Agent-Bericht (Rotphase)

Arbeitspaket: B12 „Subagenten in Ausgabe nicht sichtbar" (Bug, FEEDBACK.md)
Rolle: unabhängiger Test-Agent (`TESTER=test-agent`)
Ausgangsstand: Commit `6959136` (Branch `vibe/vibe-B12-1794587711802780115-2736030-7743`), isolierte Kopie ohne `.git` unter `/tmp/opencode/b12-redphase`.

## 1. Testherkunft

Die Testfälle wurden ausschließlich aus dem Arbeitspaket (Ticket B12), der
Akzeptanzkriterienliste (AK1–AK6) und der belegten Ursachenanalyse des
Koordinators (opencode ≥ 2.3 Background-Subagents: `state.status="completed"`
+ `state.metadata={"sessionID":…,"status":"running"}`; JSON-Stream enthält nur
Hauptsession-Ereignisse; `translate_event` setzt `part.state.status` als
Eintrag-Status; `bin/web/app.js` listet nur `running`) abgeleitet. Der
Implementierungsdiff existierte zum Zeitpunkt des Schreibens nicht; die
Produktbasis wurde direkt gelesen (`bin/vibe_runs.py`: `translate_event`,
`_capture_child_event`, `stream_events`; `bin/vibe-web.py`: `subagents_of`,
`live_subagents`, `/api/subagents`). Stil und Fixture-Muster folgen den
bestehenden B11-Suiten (`tests/unit/test_b11_stream_relay.py`,
`tests/unit/test_b11_output_view_api.py`), ohne sie zu importieren oder zu
verändern.

Keine Modellaufrufe, keine externen Dienste: Der opencode-Server ist eine
lokale HTTP-Attrappe auf 127.0.0.1 (ThreadingHTTPServer), das Dashboard läuft
in einem isolierten temporären VIBE-Root auf einem freien Port, tmux ist eine
Attrappe.

## 2. Testdatei und Testbefehl

- Datei: `tests/unit/test_b12_background_subagents.py` (neu, 913 Zeilen, 11 Tests)
- Befehl (Rotphase, gegen den Ausgangsstand):
  ```
  cd /tmp/opencode/b12-redphase && PYTHONDONTWRITEBYTECODE=1 \
    python3 -m unittest tests.unit.test_b12_background_subagents -v
  ```

## 3. Testfälle

### Teil 1 — Ereignisübersetzung (`vibe_runs.translate_event` / `stream_events`)

1. **`BackgroundSubagentTest.test_flat_running_metadata_keeps_background_subagent_running`** [AK1, AK5]
   - Vorbedingung: Hauptsession `ses_main_b12` erfasst.
   - Aktion: `tool_use` der Hauptsession, Werkzeug `task`,
     `state.status="completed"`, `state.metadata={"sessionID": "ses_kind_a",
     "status": "running"}`, Tool-Output „The subagent is working in the
     background …".
   - Erwartung: Genau ein Eintrag mit `session=ses_kind_a`, `status="running"`,
     `ended=0`, `started` int, Agent/Beschreibung/Prompt aus `state.input`,
     Ausgabe enthält den Tool-Output; Hauptsession unverändert; Zeile
     `[Subagent] code-reviewer: … — running`, keine Subagentenzeile
     `— completed`.
   - Fehlerfall: Eintrag erscheint als `completed` (Aktueller Fehler) oder
     Hauptsession verändert.

2. **`BackgroundSubagentTest.test_stream_filter_publishes_running_subagent_line`** [AK1, AK5]
   - Vorbedingung: leerer Zustand; Aufruf über `stream_events` wie in der
     Produktion.
   - Aktion: Hauptsession-Text, danach das opencode-2.3-task-Ereignis.
   - Erwartung: Genau eine Subagentenzeile im Strom, sie endet auf
     `— running`; Zustandsdatei hält einen laufenden Eintrag (`ended=0`).
   - Fehlerfall: Zeile meldet `— completed` (Aktueller Fehler).

3. **`BackgroundSubagentTest.test_background_subagent_output_is_tail_capped`** [AK1]
   - Vorbedingung: Hauptsession erfasst.
   - Aktion: task-Ereignis mit rund 70 KiB Ausgabe (ANFANG-4711/ENDE-4711) und
     Metadaten-Status `running`.
   - Erwartung: Ausgabe ≤ 64 KiB, Anfang verworfen, Ende erhalten, Status
     `running`.
   - Fehlerfall: Unbegrenztes Wachstum, Verlust des Endes oder falscher Status.

4. **`SyncLegacyBehaviorTest.test_alt_metadata_without_status_stays_completed`** [AK2]
   - Vorbedingung: Hauptsession erfasst; opencode ≤ 2.2.6-Form.
   - Aktion: task-Ereignis, `state.status="completed"`, Metadaten
     `{"metadata": {"sessionID": …}}` ohne Statusfeld.
   - Erwartung: Eintrag `completed` mit `ended > 0`; Zeile meldet
     `— completed`. (Regressionsschutz — darf sich nicht ändern.)

5. **`SyncLegacyBehaviorTest.test_flat_metadata_with_explicit_status_follows_it`** [AK2]
   - Vorbedingung: Hauptsession erfasst.
   - Aktion: flache Metadaten `{"sessionID": …, "status": "completed"}`.
   - Erwartung: Eintrag `completed`, `ended > 0`. (Regressionsschutz.)

6. **`SyncLegacyBehaviorTest.test_metadata_without_known_status_falls_back_to_tool_state`** [AK2/Fehlerfall]
   - Vorbedingung: Hauptsession erfasst.
   - Aktion: einmal flache Metadaten ohne Statusfeld, einmal mit unbekanntem
     Statuswert `wartet-auf-freigabe`; beide mit `state.status="completed"`.
   - Erwartung: jeweils `completed` mit `ended > 0`; erster Eintrag
     unverändert.
   - Fehlerfall: Unbekannter Statuswert hält den Eintrag künstlich am Laufen.

7. **`RevivalTest.test_finished_entry_is_revived_by_later_child_events`** [AK3]
   - Vorbedingung: Hauptsession erfasst; `ses_kind_a` und `ses_kind_b` über
     Alt-Form-task-Ereignisse abgeschlossen.
   - Aktion: text-, reasoning- und tool_use-Ereignisse von `ses_kind_a`.
   - Erwartung: `ses_kind_a` wieder `status="running"`, `ended=0`; Ausgabe
     enthält Abschluss-Text und neue Teilausgaben (inkl. `[Denken]` und
     `[Werkzeug]` mit Detail); `ses_kind_b` bleibt `completed`.
   - Fehlerfall: Eintrag bleibt abgeschlossen (Aktueller Fehler), Ausgabe
     geht verloren oder `ses_kind_b` wird mitbelebt.

### Teil 2 — Dashboard-Herabstufung (`/api/subagents`, `vibe-web.subagents_of`)

8. **`DashboardDowngradeTest.test_dashboard_downgrades_running_entry_when_child_is_known_and_inactive`** [AK4a]
   - Vorbedingung: laufender Registereintrag; Zustandsdatei mit Hauptsession
     und laufendem Eintrag; opencode-Attrappe meldet die Kind-Session in
     `/api/session` (`parentID` = Hauptsession), nicht in `/api/session/active`.
   - Aktion: `GET /api/subagents`.
   - Erwartung: Eintrag erscheint mit `status="completed"`.
   - Fehlerfall: Eintrag bleibt `running` (Aktueller Fehler).

9. **`DashboardDowngradeTest.test_dashboard_keeps_running_entry_when_child_is_active`** [AK4b]
   - Vorbedingung: wie 8, aber Kind-Session aktiv (`type: "running"`).
   - Erwartung: Eintrag bleibt `running`. (Regressionsschutz.)

10. **`DashboardDowngradeTest.test_dashboard_keeps_running_entry_without_password`** [AK4c]
    - Vorbedingung: wie 8, aber keine Kennwortdatei.
    - Erwartung: Eintrag bleibt `running`; kein HTTP-Aufruf an die Attrappe
      (kein erfundener Abschluss). (Regressionsschutz.)

11. **`DashboardDowngradeTest.test_dashboard_keeps_running_entry_when_server_fails`** [AK4c/Fehlerfall]
    - Vorbedingung: wie 8, aber Attrappe antwortet mit 500 (Server
      unbrauchbar). Grenze dieses Falls: Eine hart verweigerte Verbindung
      (connection refused) ist mit dem gemeinsamen Fixture-Server nicht
      abbildbar; der 500-Fall deckt denselben Codepfad
      (`opencode_request` → `None`) ab.
    - Erwartung: Eintrag bleibt `running`.
    - Fehlerfall: Ein Serverfehler wird still als Abschluss interpretiert.

AK6 (Regressionssuiten des Koordinators: `test_b11_stream_relay`,
`test_b11_output_view_api`, `test_output_view_f19_runner`,
`test_f25_session_continue`, `test_opencode_adapter`) werden nach der
Implementierung vom Koordinator ausgeführt und sind hier nur benannt.

## 4. Rotphasenbeleg (tatsächliche Ausgabe, gekürzt)

Befehl: `cd /tmp/opencode/b12-redphase && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_b12_background_subagents -v`
Exit-Code: **1** — `Ran 11 tests ... FAILED (failures=5)`

Rote Fälle (alle an den geplanten Fix-Stellen, alle behavioral, keine
Syntax-/Umgebungsfehler):

```
FAIL: test_flat_running_metadata_keeps_background_subagent_running
    AssertionError: 'running' != 'completed'
    : Der Hintergrund-Subagent gilt fälschlich als abgeschlossen:
      {"session": "ses_kind_a", ..., "status": "completed",
       "ended": 1794588733, "output": "The subagent is working in the
       background (sessionID: ses_kind_a) ..."}
FAIL: test_stream_filter_publishes_running_subagent_line
    AssertionError: '[Subagent] code-reviewer: Reviewer-Verfügbarkeit prüfen
    — running' not found in ['[Session] ses_main_b12', 'Hauptagent',
    '[Subagent] code-reviewer: Reviewer-Verfügbarkeit prüfen — completed',
    'The subagent is working in the background (sessionID: ses_kind_a) ...']
FAIL: test_background_subagent_output_is_tail_capped
    AssertionError: 'running' != 'completed'
    : {..., "status": "completed", ..., "output": "mmmm…" (64-KiB-Tail
       korrekt: ANFANG verworfen, ENDE erhalten)}
FAIL: test_dashboard_downgrades_running_entry_when_child_is_known_and_inactive
    AssertionError: 'completed' != 'running'
    : Der Hintergrund-Subagent wurde nach Serverlage nicht herabgestuft:
      {"session": "ses_kind_a", "status": "running", "ended": 0, ...}
FAIL: test_finished_entry_is_revived_by_later_child_events
    AssertionError: 'running' != 'completed'
    : Der abgeschlossene Eintrag wurde durch Kind-Ereignisse nicht
      wiederbelebt: {..., "status": "completed", "ended": 1794588720,
      "output": "ABSCHLUSS-A-4711"}
```

Grüne Fälle in der Rotphase (Regressionsschutz, erwartungsgemäß bereits
erfüllt — sie dürfen durch die Implementierung nicht rot werden):
`test_alt_metadata_without_status_stays_completed`,
`test_flat_metadata_with_explicit_status_follows_it`,
`test_metadata_without_known_status_falls_back_to_tool_state`,
`test_dashboard_keeps_running_entry_when_child_is_active`,
`test_dashboard_keeps_running_entry_without_password`,
`test_dashboard_keeps_running_entry_when_server_fails`.

## 5. Bereinigungen

- Keine bestehenden Dateien geändert; keine bereinigten Regressionen.
- Interne Verbesserung der eigenen Testdatei vor dem Rotphasenbeleg:
  `setUp` des Dashboard-Fixtures löscht nun auch
  `opencode.password` (der AK4c-Fall „ohne Kennwort" lief sonst mit dem
  Kennwort des Vortests aus dem falschen Grund). Der abschließende
  Rotphasenbeleg oben ist mit der bereinigten Fassung entstanden.
- Ein toter Code-Ausdruck in `test_stream_filter_publishes_running_subagent_line`
  wurde vor dem Rotphasenlauf entfernt (rein kosmetisch, gleiche Assertion).

## 6. Verbleibende Lücken

- AK4 „Verbindung verweigert" ist nur als 500-Fall abgebildet (gleiche
  Codepfad-Wirkung: `opencode_request` liefert `None`); eine dedizierte
  Connection-refused-Variante würde einen zweiten Webserver-Instanzstart
  erfordern und wurde bewusst weggelassen.
- AK6-Regressionssuiten laufen nach der Implementierung (Koordinator); der
  Test-Agent führt sie vor der Grünphase erneut gegen die Implementierung aus.
- Die UI-Datei `bin/web/app.js` bleibt laut Plan unverändert und wird hier
  nicht getestet (B11-Semantik „beendete Subagenten verschwinden" bleibt
  bestehen).

## 7. Korrektur nach coding-agent-Rückmeldung (13.11.2026)

**Grund:** Struktureller Testfehler im Fall
`BackgroundSubagentTest.test_stream_filter_publishes_running_subagent_line` —
die Zustandsdatei wurde erst NACH dem Verlassen von
`tempfile.TemporaryDirectory()` geladen und geprüft; zu diesem Zeitpunkt war
`state_path` bereits gelöscht und `load_subagent_state` lieferte zwingend den
leeren Zustand. Die Zustandsprüfung war konstruktiv nie erfüllbar. Der
Befund des coding-agents wurde nachvollzogen und bestätigt.

**Änderung:** ausschließlich dieser eine Test. Der Zustands-Lauf und die
zugehörigen Assertionen wurden in den `with`-Block verlegt (direkt nach
`stream_events`), mit Strukturkommentar. Die fachlichen Assertionen sind
unverändert:

- `[Subagent] code-reviewer: Reviewer-Verfügbarkeit prüfen — running` muss im
  Strom enthalten sein;
- genau eine Subagentenzeile im Strom;
- Zustandsdatei: Eintrag `ses_kind_a` mit `status="running"`, `ended=0`.

Diff-Ausschnitt (vorher → nachher, gekürzt):

```
             emitted = []
             vibe_runs.stream_events(
                 io.StringIO(payload), emitted.append, str(state_path))
 
-        self.assertIn(
-            f"[Subagent] {AGENT}: {DESCRIPTION} — running", emitted, emitted)
-        ...
-        state = vibe_runs.load_subagent_state(str(state_path))
-        entry = next(...)
-        self.assertIsNotNone(entry, ...)
-        self.assertEqual("running", entry.get("status"), entry)
-        self.assertEqual(0, entry.get("ended"), entry)
+            # Strukturkorrektur (Coding-Agent-Rückmeldung): Die
+            # Zustandsdatei wird noch innerhalb des TemporaryDirectory
+            # gelesen und geprüft; nach dem Verlassen wäre sie bereits
+            # gelöscht. Die fachlichen Assertionen bleiben unverändert.
+            self.assertIn(
+                f"[Subagent] {AGENT}: {DESCRIPTION} — running", emitted,
+                emitted)
+            ...
+            state = vibe_runs.load_subagent_state(str(state_path))
+            entry = next(...)
+            self.assertIsNotNone(entry, ...)
+            self.assertEqual("running", entry.get("status"), entry)
+            self.assertEqual(0, entry.get("ended"), entry)
```

**Kein anderer Test verändert:** bestätigt — es wurde ausschließlich der
Codekörper von `test_stream_filter_publishes_running_subagent_line`
angefasst (Einrückung und Blockverschiebung); alle übrigen 10 Testfälle,
Fixture-Klassen, Konstanten und Event-Helfer sind byteidentisch gegenüber der
Rotphasenfassung (geprüft per Diff auf fachliche Assertionen; die einzigen
Unterschiede liegen im genannten Block).

**Neuer Rotphasenbeleg** (korrigierter Test gegen den Ausgangsstand, Commit
`6959136`, entpackt nach `/tmp/opencode/b12-redbase2`; nur die korrigierte
Testdatei hinzukopiert):

```
cd /tmp/opencode/b12-redbase2 && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.unit.test_b12_background_subagents.BackgroundSubagentTest.\
  test_stream_filter_publishes_running_subagent_line -v
Exit-Code: 1
...
FAIL: test_stream_filter_publishes_running_subagent_line
AK1/AK5: Der Stream-Filter gibt die laufende Zeile aus.
Traceback (most recent call last):
  File ".../tests/unit/test_b12_background_subagents.py", line 238, in
      test_stream_filter_publishes_running_subagent_line
    self.assertIn(
        f"[Subagent] {AGENT}: {DESCRIPTION} — running", emitted, emitted)
AssertionError: '[Subagent] code-reviewer: Reviewer-Verfügbarkeit prüfen
— running' not found in ['[Session] ses_main_b12', 'Hauptagent',
'[Subagent] code-reviewer: Reviewer-Verfügbarkeit prüfen — completed',
'The subagent is working in the background (sessionID: ses_kind_a) ...']
Ran 1 test in 0.001s
FAILED (failures=1)
```

Der korrigierte Test scheitert am Ausgangsstand weiterhin aus dem richtigen
Grund: an der **Ausgabeassertion** (Zeile meldet `— completed` statt
`— running`), genau wie in der ursprünglichen Rotphase (dort Zeile 234, gleiche
Assertion, vor jeder Zustandsprüfung). Die Strukturkorrektur ändert weder
den Rotphasengrund noch die fachlichen Erwartungen; sie stellt lediglich
sicher, dass die Zustandsprüfung nach dem Fix konstruktiv erfüllbar ist.
