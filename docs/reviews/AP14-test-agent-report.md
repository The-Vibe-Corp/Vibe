# AP14 — Testbericht des unabhängigen Test-Agenten

- Datum: 12.11.2026
- Arbeitspaket: AP14 „Komplette Überarbeitung Ausgabe" (TICKETS.md, Zeile 923)
- Arbeitsbaum: `vibe-AP14-ggbktu` (Branch `vibe/vibe-AP14-1794504445407427942-147651-9932`)
- Tester: konfigurierter `TESTER=test-agent` (`.vibe/project.env`)
- Grundlage: AP14-Ticket und `SPEC.md`; die Implementierungsdiffs wurden nicht
  als Testquelle verwendet.

## Herkunftserklärung

Die vier AP14-Testdateien stammen aus einem abgebrochenen früheren Anlauf und
lagen im Arbeitsbaum unversioniert vor (ohne Bericht). Ich habe sie als
konfigurierter Test-Agent vollständig gelesen, inhaltlich gegen das AP14-Ticket
und die Akzeptanzkriterien geprüft und hiermit übernommen und abgenommen:

| Datei | Prüfung/Änderung | Grund |
|---|---|---|
| `tests/unit/test_ap14_harness_capabilities.py` (5 Tests) | übernommen; Reinheitstest in Runde 1 vom Test-Agenten umgestellt (siehe Nachtrag Runde 1 unten) | deckt AK Harness-Fähigkeitsschicht vollständig ab |
| `tests/unit/test_ap14_output_view_api.py` (16 Tests: 14 übernommen, 2 in Reviewrunde 2 ergänzt) | übernommen; Reviewrunde 2: 2 positive Protokollmarker-Fälle ergänzt (siehe „Nachtrag (Reviewrunde 2)“ unten) | deckt AK Steuern/Continue/Live-Ausgabe auf API-Ebene ab, inkl. positiver Marker-Abdeckung der zielgenauen Zustellung |
| `tests/unit/test_ap14_runner_continue.py` (7 Tests) | unverändert übernommen | deckt AK Continue auf CLI-/Läufer-Ebene inkl. Pi-Ausschluss ab |
| `tests/browser/test_ap14_output_ui.py` (8 Tests) | geändert (1 Zeile + Kommentar) | Aufräumfehler: `tearDownClass` scheiterte an einem Chromium-Kompiliercache-Verzeichnis (`OSError: [Errno 39] Directory not empty`). Behoben mit `TemporaryDirectory(ignore_cleanup_errors=True)`. Keine Assertion wurde abgeschwächt oder entfernt. |

Nachtrag (Reviewrunde 1, 2026-11-12): Ich habe den Reinheitstest in
`tests/unit/test_ap14_harness_capabilities.py`
(`test_supports_is_pure_no_process_no_file_access`) von
Modul-Attribut-Patching (`MODULE.subprocess`) auf globale
Prozessstart-Sperren umgestellt (`subprocess.Popen`, `subprocess.run`,
`subprocess.call`, `subprocess.check_output` via `mock.patch`; die
Sperren für `os`/`builtins` blieben unverändert), damit der
Reinheitsnachweis auch ohne `import subprocess` in `vibe_harness.py`
greift. Alle Aussagen des Tests blieben erhalten; keine Assertion wurde
abgeschwächt oder entfernt. Ich habe die Suite
(`tests.unit.test_ap14_harness_capabilities`, 5 Tests) ausgeführt — grün
(5 OK, Exit 0).

Neu geschriebene Tests waren in Reviewrunde 1 nicht nötig: Alle Akzeptanzkriterien
sind durch die bestehenden Fälle abgedeckt (Zuordnung siehe unten). In Reviewrunde 2
(2026-11-12) habe ich auf die Reviewer-Beanstandung (Minor 2: fehlende positive
Abdeckung des Ziel-Markers) zwei Fälle ergänzt — siehe „Nachtrag (Reviewrunde 2)“
unten.

## Zuordnung Testfälle → Akzeptanzkriterien

### a) Hauptagent-Panel immer sichtbar
- `tests.browser.test_ap14_output_ui.MainPanelTest.test_main_agent_panel_is_always_present_even_without_subagents`
  - Vorbedingung: aktiver Lauf ohne Subagenten, Ausgabe-Tab geöffnet.
  - Aktion: Ausgabebereich betrachten.
  - Erwartung: „Hauptagent"-Panel samt Hauptausgabe (Marker) vorhanden; kein JS-Fehler.
- Ergänzend `SubagentPanelsTest` (Hauptagent-Panel bleibt neben/b nach Subagentenende sichtbar).

### b) Laufende Subagenten live als eigene Panels; vollständige Ausgabe; kein Aufbewahren
- `tests.browser.test_ap14_output_ui.SubagentPanelsTest.test_running_subagent_appears_and_disappears_after_completion`
  - Erwartung: laufender Subagent erscheint als eigenes Tab neben „Hauptagent";
    nach Abschluss (status=completed) verschwindet sein Panel aus der
    Agentenauswahl und aus der Ausgabekarte; Hauptagent bleibt.
- `tests.unit.test_ap14_output_view_api.LiveOutputTest.test_live_output_renders_the_v2_projection` /
  `…_the_legacy_projection` / `…_requests_up_to_500_messages`
  - Erwartung: Textteile unverändert, reasoning als „[Denken] ", tool-Teile als
    „[Werkzeug] <tool> — <status>: <detail>" (Detail aus state.input), Nutzer-
    Nachrichten erscheinen nicht, Abruf mit `limit=500`.

### c) Anweisungen zielgenau an Hauptagent und jeden Subagenten
- `tests.unit.test_ap14_output_view_api.SteerTargetTest` (8 Tests)
  - ohne `session` → Hauptsession (F19-Regression); mit `session` → laufender
    Subagent bzw. erfasster Subagent; explizite Hauptsession → Hauptsession;
    fremde Session → `ok:false` mit Meldung und ohne Zustellung; Pi → `ok:false`
    mit bekanntem Hinweis, keine Zustellung.
  - Beweis über aufgezeichnete `POST /api/session/<session>/prompt`-Aufrufe am
    opencode-Attrappen-Server (kein vorgetäuschter Erfolg).
- Reviewrunde 2, Protokollmarker (Label dynamisch aus dem erfassten Zustandseintrag
  abgeleitet; Vorbedingung/Aktion/Erwartung im „Nachtrag (Reviewrunde 2)“):
  `test_steer_without_session_writes_the_target_marker_to_the_run_log`
  (Hauptagent-Ziel; das Fixture erfasst keinen Agentennamen, daher nennt der Marker
  nur die Session) und
  `test_steer_to_captured_subagent_writes_the_target_marker_to_the_run_log`
  (Subagent-Ziel → Marker nennt „<Agentenname> (<Session>)“).
- `tests.browser.test_ap14_output_ui.SteerTargetTest.test_steer_label_names_the_selected_target` /
  `test_steer_send_posts_the_session_of_the_selected_panel`
  - Beschriftung wechselt mit der Panelwahl („Anweisung an Hauptagent" /
    „Anweisung an <Agentname>"); abgefangener POST `/api/steer` enthält die
    Session des gewählten Panels.

### d) Continue in derselben Session
- `tests.unit.test_ap14_output_view_api.ContinueEndpointTest` (5 Tests)
  - Token-Schutz (403), Erfolg mit exportiertem `VIBE_CONTINUE_SESSION=<id>`
    (via tmux-Attrappe), Verweigerung bei aktivem Lauf, ohne erfasste Session,
    bei Pi (nennt Pi und `--no-session`).
- `tests.unit.test_ap14_runner_continue.CliContinueExportTest` (3 Tests)
  - Ungültige Kennung → `sys.exit` mit Meldung, kein Start; gültige Kennung wird
    an den Läufer exportiert; ohne Kennung wird nichts exportiert (F27-Regression).
- `tests.unit.test_ap14_runner_continue.RunnerContinueChainTest.test_first_package_and_the_chain_start_with_the_given_session`
  - Erster Paketversuch startet mit `opencode … --session <id>`; das Folgepaket
    desselben Laufs erhält eine gültige Fortsetzungskennung; Log-Zeile
    „Fortsetzung in Session".
- `tests.browser.test_ap14_output_ui.ContinueButtonTest` (2 Tests)
  - Fortsetzen-Knopf nur bei gestopptem Lauf sichtbar und betätigbar; Klick
    sendet `POST /api/continue` mit Projektnamen; bei aktivem Lauf erscheint kein
    Knopf (über mehrere Poll-Zyklen).

### e) Harness-Kompatibilität (Fähigkeitsschicht)
- `tests.unit.test_ap14_harness_capabilities.SupportsCapabilityTest` (5 Tests)
  - `vibe_harness.supports("opencode", …)` → steer+continue wahr;
    `("pi", …)` → beides falsch; unbekannte/ungültige Namen und Fähigkeiten →
    falsch; die Abfrage ist rein (kein Prozessstart, kein Dateizugriff,
    deterministisch).
- Pi-Verhalten in UI und Web-API: `PiAvailabilityTest` (Browser: kein POST bei
  Pi, `--no-session`-Hinweis), `test_pi_steer_stays_forbidden_with_known_wording`,
  `test_continue_refuses_for_pi_with_no_session_reason`,
  `RunnerPiNeverContinuesTest.test_pi_branch_never_receives_a_session`.

### f) Regressionen F19/F24/F25
- Innerhalb der AP14-Suite: `test_steering_without_session_targets_the_main_session`
  (F19), `RunnerPlainRepeatTest` (F25-Verhalten ohne Continue, inkl. erfasste
  `ses_attempt1`), `test_without_continue_session_nothing_is_exported` (F27/F25).
- Bestehende Nachbarmodule tatsächlich ausgeführt (alle grün, siehe unten):
  `tests.unit.test_f25_session_continue`, `tests.browser.test_f24_output_tabs_ui`,
  `tests.unit.test_output_view_f19_api`, `tests.unit.test_output_view_f19_runner`.

## Ausführungsergebnisse (tatsächlich)

Arbeitsbaum: `/var/mnt/data/Dokumente/Informatik/VibeCode/_logs/worktrees/vibe-AP14-ggbktu`

1. Unit (AP14, alle drei Module):
   - Befehl: `python3 -m unittest tests.unit.test_ap14_harness_capabilities tests.unit.test_ap14_output_view_api tests.unit.test_ap14_runner_continue -v`
   - Ergebnis: **26 Tests, OK**, Exit 0 (~10 s).
2. Browser (AP14):
   - Befehl: `PLAYWRIGHT_BROWSERS_PATH=<lokal vorhandener Playwright-Browser-Cache> python3 -m unittest tests.browser.test_ap14_output_ui -v`
   - erster Lauf: 8 Tests OK, aber `tearDownClass`-Fehler (Aufräumfehler, siehe oben) → FAILED (errors=1);
     nach Korrektur (`ignore_cleanup_errors=True`): **8 Tests, OK**, Exit 0 (~36 s).
3. Regression Unit:
   - `python3 -m unittest tests.unit.test_f25_session_continue -v` → **16 Tests, OK**, Exit 0 (~9 s).
   - `python3 -m unittest tests.unit.test_output_view_f19_api tests.unit.test_output_view_f19_runner` → **19 Tests, OK**, Exit 0 (~8 s).
4. Regression Browser:
   - `PLAYWRIGHT_BROWSERS_PATH=… python3 -m unittest tests.browser.test_f24_output_tabs_ui -v` → **5 Tests, OK**, Exit 0 (~14 s).
5. Reviewrunde 2 (2026-11-12), nach Befund-Fixes (Protokollmarker-Tests;
   Ausführung im Arbeitsbaum `vibe-AP14-TMZIxV`, Fortsetzung desselben Pakets):
   - `python3 -m unittest tests.unit.test_ap14_output_view_api -v` →
     **16 Tests, OK**, Exit 0 (~4 s): 14 bestehende + 2 neue
     Protokollmarker-Fälle.
   - Kombinierter Unit-Lauf (alle drei AP14-Module) → **28 Tests, OK**,
     Exit 0 (~10 s).

Zwischenstand Rot/Grün: Alle AP14-Module sind mit der vorliegenden
(ungecommiteten) Implementierung grün. Einen beobachtbaren Rotphasen-Nachweis
gibt es für diesen Lauf nicht: Die Tests wurden im früheren Anlauf vor der
Implementierung geschrieben, ein damaliger Rotlauf wurde aber nicht
dokumentiert, und die Implementierung darf von mir nicht angetastet oder
temporär zurückgesetzt werden. **Nachtrag Reviewrunde 1:** Der
Rotphasen-Nachweis wurde nachträglich über einen temporären Worktree am
Basiscommit erbracht — siehe Abschnitt „Rotphasen-/Failing-first-Nachweis
(Reviewrunde 1)“ unten. Die Tests sind nicht attrappenhaft: Sie starten
einen echten `vibe-web`-Server bzw. Läufer in isoliertem HOME/VIBE-Root mit
eigenen Ports und prüfen echte Zustellungen/Startbefehle über Aufzeichnungen;
keine echten Modellaufrufe, keine produktive Installation, keine tmux-Sessions
in der echten Umgebung (tmux nur als aufzeichnende Attrappe im isolierten PATH).

## Umgebungsaspekte

- Die Sandbox setzt `XDG_CACHE_HOME` auf einen leeren Cache; ohne
  `PLAYWRIGHT_BROWSERS_PATH=<lokal vorhandener Playwright-Browser-Cache>`
  schlagen die Browsertests mit „Executable doesn't exist" fehl. Das ist ein
  Umgebungsaspekt, kein Paketfehler; alle Browserbefehle oben wurden mit dem
  Pfad ausgeführt.
- Der einmalige Teardown-Fehler der Browser-Tests (Chromium-Kompiliercache
  verschwand erst nach dem `rmtree`-Start) wurde in der Testdatei behoben.

## Grenzen

- Für den ursprünglichen Berichtslauf existierte kein dokumentierter
  Rotphasen-Nachweis; er wurde in Reviewrunde 1 nachgeliefert, indem die
  unveränderten Testdateien an einer isolierten Kopie des Basiscommits
  9361689 ausgeführt wurden (Abschnitt unten).
- „Live" wird in den Tests über Poll-Zyklen/SSE-Feeds mit Vorhalteseiten
  geprüft; ein Echtzeit-Latenznachweis (z. B. Sekundenänderung in der UI) ist
  nicht Bestandteil der Abnahme.
- Interaktion mit mehreren gleichzeitig laufenden Subagenten wird nur mit zwei
  erfassten Subagenten (running + completed) in der Zustandsdatei geprüft, nicht
  mit drei und mehr parallelen Live-Streams.
- Die Browser-Tests decken Desktop-Viewport 1400×1000 ab; keine
  Responsive-/Touch-Prüfung.

## Rotphasen-/Failing-first-Nachweis (Reviewrunde 1)

Datum: 2026-11-12. Nachweis ergänzt auf Beanstandung der Reviewrunde 1
(fehlender Failing-first-Beleg). Es wurden ausschließlich die vier
unveränderten AP14-Testdateien gegen eine isolierte Kopie des Basiscommits
9361689 (HEAD des Arbeitsbaums) ausgeführt; Implementierung und Testdateien im
Arbeitsbaum blieben unangetastet.

### Vorgehen

1. Temporären, losgelösten Worktree am Basiscommit erzeugt:
   `git worktree add --detach <TMPDIR>/ap14-basis 9361689` (im Arbeitsbaum
   ausgeführt; TMPDIR ist das vorbereitete temporäre Verzeichnis unter /tmp
   dieser Sandbox). Exit 0.
2. Die vier AP14-Testdateien unverändert vom Arbeitsbaum in denselben Pfad im
   Basis-Worktree kopiert; Byte-Identität je Datei mit `diff -q` geprüft
   (alle vier identisch).
3. Am Basisstand verifiziert: `vibe_harness.py` enthält keine Funktion
   `supports`, `bin/` enthält keinen Endpunkt `/api/continue` — die
   AP14-Mechanik fehlt am Basisstand also tatsächlich.
4. Unit- und Browser-Tests im Basis-Worktree ausgeführt (Kommandos unten).
5. Aufgeräumt: `git worktree remove --force <TMPDIR>/ap14-basis` (Exit 0),
   temporäres Verzeichnis entfernt; `git worktree list` enthält keinen
   ap14-rotphase-Eintrag mehr; `git status` im Arbeitsbaum unverändert
   (Implementierung uncommitet, Testdateien unversioniert, HEAD 9361689).

### Kommandos (im Basis-Worktree)

- Unit:
  `python3 -m unittest tests.unit.test_ap14_harness_capabilities tests.unit.test_ap14_output_view_api tests.unit.test_ap14_runner_continue -v`
- Browser (Browser-Cache neutral via Umgebungsvariable gesetzt, kein
  persönlicher Pfad):
  `PLAYWRIGHT_BROWSERS_PATH=<lokal vorhandener Playwright-Browser-Cache> python3 -m unittest tests.browser.test_ap14_output_ui -v`

### Ergebnisse je Modul (Basisstand 9361689)

| Modul | Tests | Fehlschläge (erwartet) | am Basisstand grün |
|---|---|---|---|
| tests.unit.test_ap14_harness_capabilities | 5 | 5 ERROR | 0 |
| tests.unit.test_ap14_output_view_api | 14 | 8 FAIL | 6 |
| tests.unit.test_ap14_runner_continue | 7 | 3 FAIL-Methoden (5 ERRORs: 4 Parametrisierungen von `test_invalid_continue_session_aborts…` + `test_valid_continue_session_is_exported…`; 1 FAIL: `test_first_package_and_the_chain_start_with_the_given_session…`) | 4 |
| tests.browser.test_ap14_output_ui | 8 | 6 FAIL | 2 |
| **Summe** | **34** | **22 fehlgeschlagene Testmethoden** (kombinierter Unit-Lauf: `FAILED (failures=9, errors=10)`) | **12** |

Tatsächliche Fehlerarten (Beispiele, exakt protokolliert):

- `test_ap14_harness_capabilities` (alle 5 ERROR):
  `AttributeError: module 'vibe_harness_ap14_under_test' has no attribute 'supports'`
  — die Fähigkeitsschicht fehlt am Basisstand, wie erwartet.
- `test_ap14_output_view_api`:
  - `test_continue_continues_the_captured_session`:
    `AssertionError: 200 != 404 : {"ok": false, "error": {"code": "not_found", …}}`
    — `/api/continue` existiert am Basisstand nicht.
  - `test_continue_refuses_for_pi_with_no_session_reason`,
    `test_continue_refuses_while_a_run_is_active`: ebenfalls 404 statt
    erwarteter Antwort des Endpunkts.
  - `test_steering_rejects_foreign_sessions_without_delivery`:
    `AssertionError: True is not false : Fremde Session wurde akzeptiert`
    — Session-Validierung fehlt.
  - `test_steering_with_session_targets_a_captured_subagent`,
    `test_steering_with_session_targets_the_running_subagent`:
    Zustellung ging an `/api/session/ses_main/prompt` statt an die
    Subagent-Session — zielgenaue Steuerung fehlt.
  - `test_live_output_renders_the_v2_projection`,
    `test_live_output_requests_up_to_500_messages`: die überarbeitete
    Live-Ausgabe fehlt.
- `test_ap14_runner_continue`:
  - `test_valid_continue_session_is_exported_to_the_runner` und die vier
    Parametrisierungen von `test_invalid_continue_session_aborts…`: ERROR
    (Continue-Validierung/Export in `cmd_run` fehlt am Basisstand).
  - `test_first_package_and_the_chain_start_with_the_given_session`:
    `AssertionError: ['ses_continue'] != []` — der Läufer startet ohne
    `--session`, die Continue-Kette fehlt.
- `tests.browser.test_ap14_output_ui` (6 FAIL, Assertionsfehler):
  `test_main_agent_panel_is_always_present…` (Hauptagent-Panel fehlt),
  `test_running_subagent_appears_and_disappears…` („Nach dem Subagenten-Ende
  fehlt das Hauptagent-Panel"), `test_steer_label_names_the_selected_target`
  (Beschriftung leer), `test_steer_send_posts_the_session_of_the_selected_panel`
  (`'ses_main' != None` — Session wird nicht gesendet),
  `test_pi_steer_is_unavailable_and_never_sends` („Bei Pi wurde trotzdem POST
  /api/steer gesendet"), `test_continue_button_is_available_when_stopped…`
  (Continue-Button fehlt).

### Am Basisstand bereits grüne Fälle (12) — Einordnung

Diese Fälle prüfen kein AP14-Verhalten, sondern bestehendes Vor-AP14-Verhalten
(Regressionsgarantie) bzw. Negativerwartungen, die der fehlende Endpunkt
zufällig erfüllt:

- Unit Regression (steer ohne `session` zielt auf Hauptsession, explizite
  Hauptsession-Steuerung, Pi-Steer-Sperre mit bekanntem Wortlaut,
  Legacy-Projektion der Live-Ausgabe; `continue`-Ablehnung ohne Token und ohne
  erfasste Session — die Negativerwartung wird am Basisstand durch die
  404-Antwort des fehlenden Endpunkts erfüllt; der eigentliche
  Endpunkt-Nachweis steckt in den FAIL-Fällen).
- Runner Regression (kein Export ohne `continue_session`, Pi-Zweig erhält nie
  `--session`, ungültige Werte ohne `continue_session` werden ignoriert,
  frischer Start ohne `continue_session`).
- Browser Regression (`continue`-Button ist aktivem Lauf verborgen und für Pi
  nicht verfügbar — am Basisstand existiert der Button generell nicht, weshalb
  die beiden Negativerwartungen zufällig erfüllt sind).

### Interpretation

Die Rotphase zeigt exakt die erwarteten fehlenden AP14-Bausteine:
`supports()`-Fähigkeitsschicht, `/api/continue`-Endpunkt, Session-Validierung
und zielgenaue Zustellung, Continue-Session-Validierung/Export und
Läufer-Kette sowie die UI-Anpassungen (Hauptagent-Panel, Subagent-Panels,
Steer-Ziel, Continue-Button). Kein Fehlschlag beruht auf einer Attrappe oder
einer Abschwächung; die 12 am Basisstand grünen Fälle sind bewusste
Regressionsfälle auf Vor-AP14-Verhalten. Damit ist der
Failing-first-Nachweis für alle 34 AP14-Tests erbracht.

Alle Befehle wurden tatsächlich ausgeführt; es wurde kein Ergebnis interpoliert.

## Nachtrag (Reviewrunde 2)

Datum: 2026-11-12. Auf den Minor-Befund 2 der Reviewrunde 2 (fehlende positive
Testabdeckung des Ziel-Markers, `bin/vibe-web.py:490-505`) habe ich als
Test-Agent in `tests/unit/test_ap14_output_view_api.py`, Klasse
`SteerTargetTest`, zwei positive Marker-Fälle ergänzt und damit den Befund
geschlossen (positiver Marker-Nachweis). Vorbedingung, Aktion, erwartetes und
tatsächliches Ergebnis je Fall („Ich habe …“):

1. `test_steer_without_session_writes_the_target_marker_to_the_run_log`
   - Vorbedingung: aktiver Lauf „proj“ (per `vibe_runs`-Start in isoliertem
     HOME/VIBE-Root), Kennwortdatei für die opencode-Attrappe vorhanden,
     Zustandsdatei mit Hauptsession `ses_main` und zwei erfassten Subagenten;
     Laufprotokoll `proj.log` vorab geleert. Das Fixture erfasst für die
     Hauptsession keinen Agentennamen.
   - Aktion: `POST /api/steer` mit Token, Body `{"name": "proj", "text":
     "Prüfe zuerst die Borderstellung"}` ohne `session`-Feld.
   - Erwartung: `ok:true`; Rückmeldung exakt „Zusatzanweisung an ses_main
     übermittelt.“; Laufprotokoll enthält genau eine Dashboard-Zeile, nämlich
     „[Dashboard] Zusatzanweisung an ses_main übermittelt: Prüfe zuerst die
     Borderstellung“ — Agentenname fehlt, daher nennt der Marker nur die
     Session.
   - Tatsächliches Ausführungsergebnis: OK (grün).
2. `test_steer_to_captured_subagent_writes_the_target_marker_to_the_run_log`
   - Vorbedingung: wie 1; Ziel ist der erfasste, laufende Subagent
     `ses_child2` mit erfasstem Agentennamen „general“.
   - Aktion: `POST /api/steer` mit Feld `session: "ses_child2"` an diese
     erlaubte Subagent-Session des aktiven Laufs.
   - Erwartung: `ok:true`; Rückmeldung „Zusatzanweisung an general
     (ses_child2) übermittelt.“; Laufprotokoll enthält genau die Zeile
     „[Dashboard] Zusatzanweisung an general (ses_child2) übermittelt:
     Prüfe zuerst die Borderstellung“.
   - Tatsächliches Ausführungsergebnis: OK (grün).

Beide Fälle nutzen dieselben Attrappen-/Fixture-Mechaniken wie die
bestehenden Fälle der Datei (lokaler opencode-Attrappen-Server,
aufzeichnende tmux-Attrappe, echtes isoliertes Projekt-Git, eigene Ports);
keine echten opencode-Prozesse, keine produktiven Konfigurationen, keine
Netzaufrufe. Die Rückmeldung habe ich in beiden Fällen wörtlich geprüft; die
Zustellung selbst ist über die aufgezeichneten
`POST /api/session/<session>/prompt`-Aufrufe der Attrappe belegt (Bestands-
fälle) und der Marker über den real geschriebenen Inhalt der Laufprotokoll-
Datei — kein vorgetäuschter Erfolg. Die Zielableitung (`target_label`) ist
dynamisch an den erfassten Zustandseintrag gekoppelt. Einen separaten
Rotlauf für diese zwei Fälle gibt es nicht: Sie ergänzen positive Abdeckung
für eine bereits implementierte Mechanik (Marker existierte seit der
Runde-1-Korrektur ohne Testnachweis); der Failing-first-Nachweis der
AP14-Mechanik steht im Abschnitt „Rotphasen-/Failing-first-Nachweis
(Reviewrunde 1)“.

Ausführung (tatsächlich, Arbeitsbaum `vibe-AP14-TMZIxV`):
- `python3 -m unittest tests.unit.test_ap14_output_view_api -v` →
  **16 Tests, OK**, Exit 0 (~4 s) — Fallzahl wie in Reviewrunde 2 erwartet
  (vorher 14, neu 16).
- `python3 -m unittest tests.unit.test_ap14_harness_capabilities
  tests.unit.test_ap14_output_view_api tests.unit.test_ap14_runner_continue`
  → **28 Tests, OK**, Exit 0 (~10 s).

Alle Befehle wurden tatsächlich ausgeführt; es wurde kein Ergebnis
interpoliert. Keine bestehende Assertion wurde abgeschwächt und kein Test
gelöscht.
