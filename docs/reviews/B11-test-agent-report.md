# B11 — Bericht des unabhängigen Test-Agenten

Datum: 2026-11-13
Autor: Test-Agent (`TESTER=test-agent`, konfiguriert in `.vibe/project.env`)
Arbeitspaket: B11 „AP14 is a mess" (FEEDBACK.md) — Stopp beendet Agenten
wirklich, Subagent-Ausgabe live sichtbar, Ausgabeansicht von Grund auf neu.
Repositorium: `vibe`, Zweig `vibe/vibe-B11-1794554087900794274-1779494-9823`.

Der Bericht dokumentiert Testherkunft, Rotphasenbelege, jede Bereinigungs­entscheidung
gegenüber Alt-Tests der verworfenen Ausgabeansicht und die tatsächlich
ausgeführten Prüfungen. Implementierungsdateien wurden vom Test-Agenten nicht
verändert.

---

## 1. Testherkunft

Die fünf B11-Testdateien stammen aus einem früheren Lauf des unabhängigen
Test-Agenten (TDD-Rotphase, vor der B11-Umsetzung geschrieben). Der aktuelle
Test-Agent hat sie vollständig gelesen, gegen FEEDBACK.md (Abschnitt B11),
SPEC.md („Agentenläufe und Prüfungen", „App und opencode beenden") und
TICKETS.md (AP14-Eintrag als Kontext des verworfenen Zustands) geprüft und
folgende Bereinigungen an den Alt-Tests vorgenommen (Kapitel 3). Die B11-Tests
selbst wurden **nicht** abgeschwächt, umgeschrieben oder gelöscht.

| Datei | Tests | Herkunft |
|---|---|---|
| `tests/unit/test_b11_stop_terminates_agents.py` | 8 | Test-Agent (vorheriger Lauf) |
| `tests/unit/test_b11_stream_relay.py` | 6 | Test-Agent (vorheriger Lauf) |
| `tests/unit/test_b11_output_view_api.py` | 8 | Test-Agent (vorheriger Lauf) |
| `tests/browser/test_b11_output_ui.py` | 8 | Test-Agent (vorheriger Lauf) |
| `tests/unit/runner_fixtures/b11_harness.py` | — | Test-Doppel, zum Stopp-Test gehörend |
| `tests/unit/runner_fixtures/b11_child.py` | — | Test-Doppel |
| `tests/unit/runner_fixtures/b11_grandchild.py` | — | Test-Doppel |

## 2. Prüfung der B11-Tests gegen Ticket und SPEC

Geprüft wurde unabhängig vom Implementierungsdiff (der nur in `bin/vibe-run.sh`
vorhandene, unvercommittete Stopp-Umsetzungsentwurf wurde nicht als
Testgrundlage verwendet; er wurde weder gelesen als Vorlage noch verändert).

### 2.1 Abdeckung der Ticketanforderungen

**B11-Punkt 1 — „stop button … agents still continue (this is a no go)"**
(aus FEEDBACK.md) plus SPEC „gezielt stoppen" und „Ein äußeres Signal (HUP,
TERM, INT) beendet einen Lauf nicht spurlos … Registerzustand wird
festgehalten":

- `StopKillsAgentTest` (3 Fälle): signalignorierender Harness als
  `opencode`-Doppel, Unter- und Enkelprozess; HUP und TERM jeweils an die
  Prozessgruppe; KILL-Eskalation bei gleichzeitiger HUP/TERM-Ignoranz.
  Beobachtbar geprüft: Läufer tot, alle PIDs tot, keine weiteren
  Arbeitsticks (Ticks-Zählerstand vor/nach dem Warten).
- `SignalRegistryTest` (2 Fälle): Registereintrag `ended` (nie `running`),
  Notiz „extern beendet (Signal HUP)", Exit-Code 129, Protokollzeile;
  bereits `finished` gesetzter Eintrag wird nicht überschrieben (only-live).
- `NormalRunBehaviourTest` (2 grüne Anker): reguläres Signalverhalten bleibt
  (129, Protokollzeile, Notiz) und Agenten-Exit-Code stammt aus der Pipeline
  (`PIPESTATUS`), nicht von `tee`.
- `StopEndpointRealTmuxTest`: echter Lauf in echter tmux-Sitzung
  (eigener Socket, isoliertes `TMUX_TMPDIR`), `vibe stop proj` — der Weg,
  den `/api/stop` ebenfalls nimmt — beendet Sitzung und Prozesskette,
  Registereintrag endet, `run_state` meldet keinen aktiven Agenten.

Fehlerpfade sind abgedeckt (Signalignoranz, Eskalation, Fremd-`finish`,
Pipeline-Exitcode-Verfälschung). Bewertung: ausreichend.

**B11-Punkt 2 — Subagent-Ausgabe live sichtbar:**

- `test_b11_stream_relay.py` (6 Fälle, AK7/AK6): fremde `sessionID` legt
  laufenden Subagenten mit Teilausgabe (Text/`[Denken]`/`[Werkzeug]`) an;
  zwei parallele Kinder getrennt erfasst; `task`/`completed` beendet genau
  das zugehörige Kind; Hauptsession-Ereignisse erfinden keine Subagenten;
  defekte JSON-Zeilen beschädigen Stream und Zustand nicht; Zustandsdatei
  bleibt begrenzt (≤ 50 Einträge, < 256 KiB), laufende Einträge bleiben.
- `test_b11_output_view_api.py` (AK6): `/api/subagents` nur Einträge des
  aktuellen Laufs, neueste zuerst, ohne überdimensionale `prompt`-Felder;
  `/api/subagent-output` chronologisch (Abruf mit `order=asc`), unbekannte
  Session wird ohne Serverabfrage abgelehnt; Regressionen für
  `/api/steer`-Zielauswahl und `/api/continue`-Ablehnung.
- `test_b11_output_ui.py` (AK1–AK5 des UI-Vertrags): Hauptagent und zwei
  laufende Subagenten **gleichzeitig** sichtbar (kein Tabwechsel),
  Live-Verlängerung ohne Panelwechsel, beendeter Subagent verschwindet,
  zielgenaue Anweisung per `select[aria-label='Ziel']`, Tastaturbedienung,
  „Fortsetzen" nur bei gestopptem Lauf, verfügbare Höhe, keine Modale,
  keine alten Bausteine (`steer-card`, `logcard`, `outtabs`, `output-layout`,
  `outpane`, Tablisten) mehr.

Bewertung: ausreichend; beide Seiten (Erfassung im Läuferfilter und
Darstellung in der UI) und die vereinbarten Backend-Anpassungen sind
getestet.

### 2.2 Festgestellte Unstimmigkeiten (ohne Abdeckungsmangel)

1. **AK-Nummerierung ist dateilokal, nicht global einheitlich.** Im
   Stopp-Test bedeutet AK1 „Stopp beendet die Prozesskette", im
   UI-Test bedeutet AK1 „Hauptagent und Subagenten gleichzeitig sichtbar";
   AK6/AK7 existieren nur in den Backend-Dateien. Die Zuordnung ist je
   Datei in sich schlüssig (jeder Fall nennt in seinem Docstring Vorbedingung,
   Aktion, Erwartung und Fehlerfall), aber eine projektweite AK-Nummerierung
   existiert nicht. Notiert, nicht geändert — inhaltlich ordnet jeder Fall
   sich eindeutig FEEDBACK.md/SPEC.md zu.
2. **Doppelte Teilbezeichnung**: `test_b11_stream_relay.py` und
   `test_b11_output_view_api.py` nennen sich beide „Unit-Abnahme B11
   (Teil 2)". Kosmetisch; keine Auswirkung auf die Abdeckung.
3. **Offene Semantik „kein Lauf registriert"**: Die vereinbarte Änderung
   „`/api/subagents` liefert nur Einträge des aktuellen Laufs" ist für den
   Fall definiert, dass ein Lauf registriert ist. Für den Fall „kein
   Registereintrag" (kein Lauf je/gestoppt) ist das Verhalten nicht
   vereinbart. Die B11-Tests pinnen diesen Fall nicht; die betroffenen
   Alt-Tests wurden an den definierten Fall angepasst (Kapitel 3.4, 3.5).
   Der Reviewer sollte beachten, dass die Umsetzung den undefinierten
   Fall nicht stillschweigend als „zeige alles" interpretieren darf,
   weil das der Begründung „keine Überbleibsel früherer Läufe"
   widerspräche.
4. **Keine zusätzliche B11-Testlücke gefunden.** Insbesondere wurden keine
   Tests nachgeschrieben, um Umsetzungswünsche zu ersetzen. Ein bewusst
   verbleibender Rest: Für den „Stopp"-Knopf auf Projektebene existiert kein
   Browser-Test der Schaltflächen-Verkabelung (Klick → `POST /api/stop`).
   Der Stopp-Pfad selbst ist über `StopEndpointRealTmuxTest` (`vibe stop`,
   derselbe Weg wie `/api/stop`) abgedeckt; die Knopf-Verkabelung ist
   Bestandsfunktionalität vor B11 und nicht Teil des neuen UI-Vertrags.
   Als verbleibende Lücke dokumentiert (Kapitel 5).

### 2.3 Rotphasenbeleg

Gemessen am Arbeitsstand (Umsetzungsentwurf `bin/vibe-run.sh` unvercommittet
vorhanden; Ausgabeansicht noch die AP14-Bausteine):

- B11 Unit-Suite (`discover -p 'test_b11_*.py'`): **22 Tests, 13 ok,
  9 Failures, Exit 1.**
  - Rot (9): `test_child_session_events_create_a_running_subagent_with_output`,
    `test_two_child_sessions_are_tracked_in_parallel`,
    `test_task_completion_ends_the_matching_child_only`,
    `test_broken_lines_do_not_break_capture`,
    `test_state_file_stays_bounded_with_many_finished_subagents`
    (Stream-Relay, 5),
    `test_subagents_only_lists_entries_of_the_current_run`,
    `test_subagents_are_sorted_newest_first`,
    `test_subagents_payload_carries_no_oversized_prompt`,
    `test_subagent_output_is_chronological_and_requests_ascending` (API, 4).
  - Grün (13): alle 8 Stopp-Tests (die Prozessgruppen-Umsetzung liegt als
    unvercommitteter Entwurf vor; die Rotphase dieser 8 Fälle vor diesem
    Entwurf kann vom Test-Agenten nachträglich nicht mehr reproduziert
    werden, ohne die fremde Arbeitskopie zu verändern — dokumentiert,
    nicht belegt), sowie „keine erfundenen Subagenten", beide
    `/api/steer`-Regressionen, `/api/continue`-Ablehnung und die
    unbekannte-Session-Ablehnung (diese Semantiken bestehen bereits aus
    F19/AP14 und sind grüne Anker).
- B11 Browser-Suite (`tests.browser.test_b11_output_ui`, Playwright,
  Chromium): **8 Tests, 1 ok, 7 Failures, Exit 1.** Rot: beide
  Gleichzeitigkeit-Fälle, beide Steer-Fälle, Höhen-Nutzung,
  Altbausteine-Entfernung, „Fortsetzen" versteckt bei aktivem Lauf.
  Bereits grün (Übereinstimmung mit dem AP14-Bestand, kein Beweis der neuen
  Ansicht): „Fortsetzen"-Knopf erscheint bei gestopptem Lauf.
  Der Playwright-Browser war verfügbar (`~/.cache/ms-playwright`); keine
  Umgebungsgrenze zu vermerken.

## 3. Bereinigung der Alt-Tests der verworfenen Ausgabeansicht

Alle Entscheidungen im Überblick; Begründung je Fall. Grundsatz: Nur
Testfälle der **Oberfläche** der verworfenen F19/F24/AP14-Ansicht wurden
entfernt oder angepasst. Bestehende Backend-Semantik, die im neuen Vertrag
weiter besteht (Steuerung, Continue, Fähigkeitsschicht, Läuferprotokoll,
Agentenmeldung), blieb als Regression erhalten. B11-Testfälle wurden
nirgends abgeschwächt; es wurde nichts entfernt, um
Implementierungsmängel zu verdecken.

Vor der Bereinigung waren alle betroffenen Suiten am Ausgangsstand grün
(gemessen, Kapitel 4). Die Browser-Dateien prüften die Oberfläche der
aktuellen (AP14-)Implementierung, die B11 ausdrücklich verwirft.

### 3.1 `tests/browser/test_ap14_output_ui.py` — GELÖSCHT (8 Tests)

Die Datei prüft ausschließlich die Oberfläche der verworfenen AP14-Ansicht
(Tabs/Panel-Mechanik, Steuerkarten-Beschriftung, Fortsetzen-Knopf, Pi-Hinweis).
Kein Testfall darin ist reine Backend-Semantik (alle nutzen Playwright).
Einzelfallentscheidung:

| Fall | Entscheidung | Begründung / Abdeckung |
|---|---|---|
| a `test_main_agent_panel_is_always_present_even_without_subagents` | entfernt | Oberfläche der alten Ansicht; im neuen Vertrag durch `test_b11_output_ui` abgedeckt (Hauptansicht mit `data-role='main'` ist immer vorhanden; u. a. `ContinueTest.test_continue_button_is_hidden_while_a_run_is_active` wartet ohne Subagenten auf die Hauptansicht). |
| b `test_running_subagent_appears_and_disappears_after_completion` | entfernt | Tab-/Panelmechanik der verworfenen Ansicht; neu abgedeckt durch B11-Fälle 1 (gleichzeitig sichtbar) und 2 (beendet → verschwindet). |
| c `test_steer_label_names_the_selected_target` | entfernt | UI-Beschriftung der verworfenen Steuerkarte; der neue Vertrag schreibt `select[aria-label='Ziel']` vor und verlangt diese Beschriftung nicht. Zielsemantik bleibt an der API (B11-API-Regression) und im B11-UI-Test 3 geprüft. |
| d `test_steer_send_posts_the_session_of_the_selected_panel` | entfernt | Neuer Vertrag: B11-UI-Test 3 (`test_steer_target_selection_posts_the_chosen_session`) prüft exakt dies (POST mit gewählter Session) gegen die neue Ansicht. |
| e `test_continue_button_is_available_when_stopped_and_posts_continue` | entfernt | Neuer Vertrag: B11-UI-Test 5 prüft Knopf und POST `/api/continue` gegen die neue Ansicht. |
| f `test_continue_button_is_hidden_while_a_run_is_active` | entfernt | Neuer Vertrag: B11-UI-Test 6. |
| g `test_pi_steer_is_unavailable_and_never_sends` | entfernt | UI-Teil (Hinweistext `--no-session` in der Ausgabeansicht) ist Oberfläche der verworfenen Ansicht. Die fachliche Pi-Sperre bleibt an der API geprüft: `tests/unit/test_ap14_output_view_api.py::SteerTargetTest.test_pi_steer_stays_forbidden_with_known_wording` (behalten) und die Fähigkeitsschicht `tests/unit/test_ap14_harness_capabilities.py` (behalten). |
| h `test_pi_continue_is_unavailable_when_stopped` | entfernt | wie g; API-seitig abgedeckt durch `test_ap14_output_view_api.py::ContinueEndpointTest.test_continue_refuses_for_pi_with_no_session_reason` (behalten). |

### 3.2 `tests/browser/test_f24_output_tabs_ui.py` — GELÖSCHT (5 Tests)

Alle fünf Fälle prüfen die nur-aktiver-Tab-Mechanik und die Agenten-Pille der
verworfenen Ansicht — genau die Bausteine, die der B11-UI-Vertrag
ausdrücklich verbietet („keine Agenten-Tabliste im Ausgabebereich",
„gleichzeitige Ansichten ohne Tabwechsel"). Kein reiner Backend-Fall
darin; die API-Semantik „aktiver Lauf meldet den registrierten Agenten"
wird von `tests/unit/test_f24_output_agent_ui.py` (behalten, 5 Tests)
weiter geprüft.

| Fall | Entscheidung | Begründung |
|---|---|---|
| a `test_active_agent_is_shown_in_the_output_area` | entfernt | UI-Pille `#agent-active` der verworfenen Ansicht; API-Teil bleibt in `test_f24_output_agent_ui.py` erhalten. |
| b `test_parallel_agents_get_one_tab_each` | entfernt | widerspricht dem neuen Vertrag (Tabliste verboten; gleichzeitige Ansichten). |
| c `test_tab_switch_loads_the_subagent_output` | entfernt | Tabwechsel-Mechanik ist verboten; neue Ansicht zeigt alles gleichzeitig (B11-UI-Test 1). |
| d `test_finishing_a_subagent_closes_its_tab` | entfernt | Neu: Ansicht verschwindet (B11-UI-Test 2); „Tab schließt" ist verworfene Mechanik. |
| f `test_keyboard_navigation_through_agent_tabs` | entfernt | Tab-Tastaturnavigation der verworfenen Ansicht; der neue Vertrag prüft Tastaturbedienung von Zielauswahl und Senden (B11-UI-Test 4). |

### 3.3 Unit-Dateien ohne Kollision — BEHALTEN (unverändert)

| Datei | Entscheidung | Begründung |
|---|---|---|
| `tests/unit/test_ap14_output_view_api.py` (16 Tests) | behalten, unverändert | Reine Backend-Semantik, die im B11-Vertrag weiter besteht: `/api/steer`-Ziele (Hauptsession, erfasster Subagenten, auch abgeschlossener), Protokollmarker, Fremd-Ablehnung, Pi-Sperre, `/api/continue` inkl. Token-Schutz, `VIBE_CONTINUE_SESSION`-Export, aktiver-Lauf-Ablehnung, Live-Ausgabe-Rendering (v2-/Alt-Projektion, `[Denken]`/`[Werkzeug]`-Zeilen, `limit=500`). Kein Fall widerspricht der vereinbarten B11-Änderung (Aktualität, Sortierung, Prompt-Kürzung, `order=asc`); `limit=500` und `order=asc` schließen sich nicht aus. Hinweis an den Coding-Agenten: Falls die Umsetzung das Steuern eines *abgeschlossenen* erfassten Subagenten einschränkt oder `limit=500` aufgibt, ist das eine Semantikänderung über den vereinbarten Umfang hinaus und muss neu vereinbart werden, nicht still durch Testanpassung. |
| `tests/unit/test_ap14_harness_capabilities.py` (5 Tests) | behalten | Fähigkeitsschicht (`supports()`), kein Bezug zur Ansichtsoberfläche. |
| `tests/unit/test_ap14_runner_continue.py` (7 Tests) | behalten | CLI-Export von `VIBE_CONTINUE_SESSION`, Läufer-Kette, Pi-Branch ohne Session — erhalten gebliebene Backend-Semantik. |
| `tests/unit/test_output_view_f19_runner.py` (5 Tests) | behalten | Läuferprotokoll (`--format json`, menschenlesbare Zeilen) und Aufgaben-Erfassung in der Zustandsdatei bleiben Vertragsgrundlage; der B11-Stream-Relay *ergänzt* die Erfassung live aus Kind-Sessions, er ersetzt die `task`-Ereignissemantik nicht. |
| `tests/unit/test_f24_output_agent_ui.py` (5 Tests) | behalten | „Aktiver Lauf meldet den registrierten Agenten (neuester Registereintrag, LIVE-Zustände)“ bleibt bestehen; der B11-UI-Vertrag widerspricht dem nicht. |
| `tests/unit/test_b6_pi_runner_events.py` (4 Tests) | behalten | Pi-Läufer-Ereignisübersetzung, Exit-Code — unberührt von B11. |
| `tests/unit/test_b6_harness_events_flag.py` (6 Tests) | behalten | Harness-Argv (`--events`/JSON-Modus) — unberührt von B11. |
| `tests/unit/test_b6_pi_events.py::OpencodeRegressionTest` (2 Tests) | behalten | Byte-gleiche opencode-Stream-Zeilen und die exakte Eintragsform (dict-Vergleich) bleiben Regression. Hinweis: Falls die B11-Umsetzung der Zustandsdatei neue Felder hinzufügt, verletzt das diesen Vertrag und ist neu zu vereinbaren — nicht still abzuschwächen. |

### 3.4 `tests/unit/test_output_view_f19_api.py` — 2 Fälle ANGEPASST (14 Tests gesamt)

| Fall | Entscheidung | Begründung |
|---|---|---|
| `SubagentsEndpointTest.test_subagents_reports_state_file_entries` | angepasst | Kollision mit der vereinbarten Semantik „nur Einträge des aktuellen Laufs": Der Fall registrierte keinen Lauf und lieferte Einträge mit `started: 1/3`. Neu: Es wird ein laufender Lauf registriert (`start_active_run`) und die Startzeiten der erfassten Einträge hinter den Laufbeginn gesetzt; die Feldsemantik (Session, Agent, Beschreibung, Status, Ausgabe) wird je Session geprüft, unabhängig von der Sortierung (die Sortierung pinnen die B11-Tests). |
| `SubagentOutputTest.test_output_of_a_captured_subagent` | angepasst | Derselbe Aktualitätsbezug für `/api/subagent-output`: laufender Lauf registriert, Startzeit des erfassten Eintrags hinter den Laufbeginn; Erwartung (gespeicherte Ausgabe „PONG“) unverändert. |
| alle übrigen 12 Fälle | behalten, unverändert | Token-Schutz, leere Liste ohne Zustandsdatei, unbekannte Session (`ok:false`), laufender Subagent ohne Live-Daten, Steuerungs-Regressionen (Zustellung, Ablehnungen, Kennwort-Schutz) — bleiben geltende Semantik. |

### 3.5 `tests/unit/test_b6_pi_events.py::PiSubagentApiTest` — 2 Fälle ANGEPASST (24 Tests gesamt)

| Fall | Entscheidung | Begründung |
|---|---|---|
| `test_pi_captured_subagent_appears_in_ui_api` | angepasst | Derselbe Aktualitätsbezug wie 3.4: Die Pi-erfassten Einträge gehören zum aktuellen Lauf, wenn der Lauf registriert ist, bevor der echte Übersetzungsfilter sie erfasst. Der Fall registriert jetzt den Lauf (`register_run`, echtes `vibe_runs.py start`), bevor `stream` die Zustandsdatei erzeugt. Erwartungen (toolCallId-Session, Status, Agent, Beschreibung, Ausgabe, keine erfundene Hauptsitzung) unverändert. |
| `test_pi_subagent_output_served_by_ui_api` | angepasst | wie oben (Lauf registriert vor der Erfassung); Erwartungen unverändert. |
| übrige 22 Fälle der Datei | behalten | Pi-Ereignisübersetzung und Stream-Formregeln sind von B11 unberührt. |

### 3.6 `tests/browser/test_f20_harness_ui.py` — 2 Fälle ENTFERNT, 1 Fall ANGEPASST (12 → 10 Tests)

Nicht in der Aufzählung des Arbeitspakets, aber dieselbe Kollision: Die F20-
Fälle prüften Pi-Wortwahl an `#steer-card`/`#subagents-card` — Karten der
verworfenen Ausgabeansicht, die der B11-Vertrag entfernt.

| Fall | Entscheidung | Begründung |
|---|---|---|
| `test_steer_card_names_pi_print_limit` | entfernt | Nur-Oberfläche (`#steer-card` im Ausgabe-Tab); die fachliche Pi-Sperre bleibt an der API geprüft (`test_ap14_output_view_api.py::SteerTargetTest.test_pi_steer_stays_forbidden_with_known_wording`, behalten). Die F20-Wortwahl auf der neuen Ansicht ist nicht Teil des B11-Vertrags. |
| `test_subagent_card_notes_pi_limit` | entfernt | Nur-Oberfläche (`#subagents-card`); Pi-Fähigkeiten bleiben in `test_ap14_harness_capabilities.py` und den API-Ablehnungen geprüft. |
| `OpencodeRegressionUiTest.test_detail_link_and_cards_keep_opencode_wording` | angepasst | Der Ausgabe-Tab-Abschnitt („opencode-Session“ in `#steer-card`, `#subagents-card` ohne Pi-Hinweis) prüfte die verworfene Ansicht und ist entfernt; die übrigen Regressionen (Link „opencode-Weboberfläche“, Sandbox-Wortlaut „opencode-Server in bubblewrap“, „Voreingestellt sind /tmp/opencode“) bleiben unverändert erhalten. |
| übrige 9 Fälle | behalten | Kopfleiste, Modelle, Profile, Agenten-Hinweis, MCP-Hinweis, Sandbox — ohne Ausgabeansicht-Bezug. |

### 3.7 B10-Tests — NICHT VORHANDEN

`tests/unit/test_b10_*.py` existieren in diesem Arbeitsbaum nicht. B10
(commit `74082ec`/`e2ee214`, Zweig `feature/b10-f24-sichtbarkeit`) ist im
Basenbaum dieses B11-Zweigs nicht enthalten (`git merge-base --is-ancestor`
: nein; AP14/AP15 sind über eine eigene Transfer-Linie transferiert). Es
gibt also keinen B10-Test, der bereinigt oder angepasst werden müsste. Sollte
die B10-Linie später in diesen Baum übertragen werden, ist Kapitel 3 dieser
Bereinigung auf sie anzuwenden (B10-Tests prüfen die F24-Bausteine
`<log>.opencode.json`-Speisung der alten Ausgabekarte).

## 4. Tatsächlich ausgeführte Prüfungen

Alle Befehle wurden im Repositorium (FUSE/NTFS-Arbeitsbaum) mit `bash`
ausgeführt; keine Modellaufrufe, keine produktive Installation, isolierte
Ports/Verzeichnisse in den Tests.

### 4.1 B11 Unit-Suite

```
python3 -m unittest discover -s tests/unit -p 'test_b11_*.py'
→ Ran 22 tests in 18.742s
→ FAILED (failures=9), Exit-Code 1
```
Erwartung erfüllt: 13 ok / 9 Failures (Kapitel 2.3). Verbose-Durchlauf
bestätigt die 9 roten Fälle namentlich.

### 4.2 B11 Browser-Suite (Playwright, Chromium)

```
PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
python3 -m unittest tests.browser.test_b11_output_ui
→ Ran 8 tests in 146.615s
→ FAILED (failures=7), Exit-Code 1
```
Dokumentierte Rotphase (Kapitel 2.3). Playwright-Browser vorhanden; keine
Umgebungsgrenze.

### 4.3 Bereinigte/betroffene Alt-Suiten (nach der Bereinigung)

```
python3 -m unittest tests.unit.test_output_view_f19_api
→ Ran 14 tests, OK, Exit 0            (2 Fälle angepasst)
python3 -m unittest tests.unit.test_output_view_f19_runner
→ Ran 5 tests, OK, Exit 0             (unverändert)
python3 -m unittest tests.unit.test_f24_output_agent_ui
→ Ran 5 tests, OK, Exit 0             (unverändert)
python3 -m unittest tests.unit.test_ap14_output_view_api
→ Ran 16 tests, OK, Exit 0            (unverändert)
python3 -m unittest tests.unit.test_ap14_harness_capabilities
→ Ran 5 tests, OK, Exit 0             (unverändert)
python3 -m unittest tests.unit.test_ap14_runner_continue
→ Ran 7 tests, OK, Exit 0             (unverändert)
python3 -m unittest tests.unit.test_b6_pi_events
→ Ran 24 tests, OK, Exit 0            (2 Fälle angepasst)
python3 -m unittest tests.unit.test_b6_pi_runner_events
→ Ran 4 tests, OK, Exit 0             (unverändert)
python3 -m unittest tests.unit.test_b6_harness_events_flag
→ Ran 6 tests, OK, Exit 0             (unverändert)
python3 -m unittest tests.browser.test_f20_harness_ui
→ Ran 10 tests, OK, Exit 0            (2 entfernt, 1 angepasst)
```

Vor der Bereinigung waren alle diese Suiten am unveränderten Stand ebenfalls
grün (gemessen; 12/8/5 Browser-Fälle und die Unit-Zahlen oben) — die
Anpassungen beschädigen keine bestehende Abdeckung.

### 4.4 Syntaxprüfung

```
python3 scripts/check-syntax.py
→ OK: 155 Python-, 8 Bash- und 4 JSON-Datei(en) syntaktisch geprüft. Exit 0
```

## 5. Verbleibende Lücken und Hinweise

1. **Kein Browser-Test der Stopp-Schaltfläche** auf Projektebene (Klick →
   `POST /api/stop`). Der Stopp-Pfad ist über `StopEndpointRealTmuxTest`
   (`vibe stop`, derselbe Weg wie `/api/stop`) und die Prozessketten-Tests
   abgedeckt; die Schaltflächen-Verkabelung ist Bestandsfunktionalität vor
   B11. Wenn der Reviewer die Schaltfläche im B11-Umfang sehen will, ist
   das als Folgetest zu beauftragen — nicht still wegzulassen.
2. **Undefinierte Semantik „kein Registereintrag“** für `/api/subagents`/
   `/api/subagent-output` (Kapitel 2.2, Punkt 3). Die Umsetzung sollte den
   Fall mit dem Reviewer klären; die Alt-Tests wurden auf den
   definierten Fall (laufender Lauf registriert) umgestellt, pinnen den
   undefinierten Fall aber bewusst nicht.
3. **Rotphase des Stopp-Tests nicht mehr reproduzierbar**: Die 8 Stopp-Tests
   sind am aktuellen Arbeitsbaum grün, weil die Stopp-Umsetzung
   (Prozessgruppen-Isolation + KILL-Eskalation in `bin/vibe-run.sh`) als
   unvercommitteter Entwurf vorliegt. Die ursprüngliche Rotphase dieser
   Fälle wurde vom vorherigen Test-Agenten-Lauf belegt (Gesamtstatus
   13 ok / 9 Failures vor dem Entwurf lt. Meldung des Primär-Auftrags); der
   aktuelle Test-Agent kann sie nicht nachweisen, ohne die fremde
   Arbeitskopie zurückzusetzen. Die übrigen 14 roten Fälle (Stream-Relay 5,
   API 4, Browser 7 — Summe 16 rote Einzelfälle über Unit+Browser) sind am
   aktuellen Stand gemessen.
4. **Vertragsdetails, deren Änderung neu vereinbart werden muss** (nicht
   still durch Testanpassung): Steuern abgeschlossener erfasster
   Subagenten, `limit=500` beim Nachrichtenabruf, exakte Feldliste eines
   Zustandsdatei-Eintrags (B6-Byte-Vergleich). Siehe Kapitel 3.3.
5. Die B10-Tests sind in diesem Baum nicht vorhanden (Kapitel 3.7); eine
   spätere Übertragung der B10-Linie muss die Bereinigung nachziehen.

## 6. Geänderte/gelöschte Dateien des Test-Agenten

- Gelöscht: `tests/browser/test_ap14_output_ui.py` (8 Fälle),
  `tests/browser/test_f24_output_tabs_ui.py` (5 Fälle).
- Angepasst: `tests/unit/test_output_view_f19_api.py` (2 Fälle + Konstante
  `CHILD_RUNNING`), `tests/unit/test_b6_pi_events.py` (2 Fälle, neuer
  Fixture-Helfer `register_run`), `tests/browser/test_f20_harness_ui.py`
  (2 Fälle entfernt, 1 Fall angepasst).
- Neu (vom vorherigen Test-Agenten-Lauf, unverändert übernommen und geprüft):
  `tests/unit/test_b11_stop_terminates_agents.py`,
  `tests/unit/test_b11_stream_relay.py`,
  `tests/unit/test_b11_output_view_api.py`,
  `tests/browser/test_b11_output_ui.py`,
  `tests/unit/runner_fixtures/b11_{harness,child,grandchild}.py`.
- Produktionsdateien wurden vom Test-Agenten nicht verändert; nichts
  committed.


---

## 7. Runde 2 — Nachträge zum Review (B11-review-1.md)

Datum: 2026-11-13. Auftrag: Behebung der Review-Befunde Medium 1–4 und
Minor 2/4 aus der Test-Agenten-Perspektive — Rotphasenprotokoll für die
8 Stamm-Stopp-Tests (Medium 4), neue Testfälle für die Befunde Medium 1–3
und Minor 2/4, Regressionen. Implementierungsdateien wurden weiterhin nicht
verändert; geändert wurden ausschließlich die drei B11-Unit-Testdateien und
dieser Bericht.

### 7.1 Rotphasenprotokoll A — die 8 Stamm-Stopp-Tests gegen den Ausgangsstand

Verfahren (Medium 4): Der Ausgangscommit des Pakets (`b46b98d`) wurde mit
`git archive b46b98d | tar -x` in das isolierte Prüfverzeichnis
`/tmp/opencode/b11-redphase` entpackt (keine Berührung der Arbeitskopie;
die Basis enthält keine Prozessgruppen-Isolation — `grep stop_agent_group
bin/vibe-run.sh` = 0 Treffer). Dort wurden ausschließlich die Testdatei
`tests/unit/test_b11_stop_terminates_agents.py` samt der drei
Runner-Fixtures (`b11_harness.py`, `b11_child.py`, `b11_grandchild.py`)
abgelegt.

```
cd /tmp/opencode/b11-redphase && PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests.unit.test_b11_stop_terminates_agents -v
→ Ran 8 tests in 79.282s
→ FAILED (failures=6), Exit-Code 1
```

Rot (6):

* `StopKillsAgentTest.test_hup_stop_kills_agent_that_ignores_hup`
* `StopKillsAgentTest.test_term_stop_kills_agent_that_ignores_term`
* `StopKillsAgentTest.test_hup_stop_kills_agent_that_ignores_hup_and_term`
* `SignalRegistryTest.test_signal_stop_marks_the_run_ended_with_signal_note`
* `SignalRegistryTest.test_signal_stop_leaves_an_already_finished_record`
* `StopEndpointRealTmuxTest.test_stop_command_ends_the_run_and_shows_no_active_agent`

Grün (2, Anker): beide `NormalRunBehaviourTest`-Fälle — die reguläre
Signalbehandlung (129, Protokollzeile, Notiz) und der Harness-Exitcode aus
`PIPESTATUS` sind Ausgangsverhalten und beweisen die B11-Änderung nicht.

Repräsentative Fehlerauszüge (Rohprotokoll, vor der Löschung des
Prüfverzeichnisses übernommen):

```
AssertionError: Prozesse des Laufs überleben:
{'harness': 2318582, 'child': 2318585, 'grandchild': 2318586}
Der Agent arbeitet nach dem Stopp weiter (Ticks
{'child.tick': 484, 'grandchild.tick': 482, 'harness.tick': 484}
-> {'child.tick': 496, 'grandchild.tick': 494, 'harness.tick': 496})
```

```
test_stop_command_ends_the_run_and_shows_no_active_agent
AssertionError: {'harness': 2318392, 'child': 2318395, 'grandchild': 2318396} != {}
```

Damit ist die in Runde 1 nur berichtete Rotphase der 8 Stamm-Stopp-Tests
nachträglich und unabhängig belegt: Ohne Prozessgruppen-Isolation überlebt
ein HUP/TERM-ignorierender Harness samt Unter- und Enkelprozess den Stopp
und arbeitet weiter (Ticks steigen weiter); auch `vibe stop` über echte
tmux-Sitzung lässt die Kette zurück. Damit ist der Review-Befund Medium 4
ausgeräumt.

### 7.2 Neue Testfälle für Review-Befunde (zuerst geschrieben, dann am
aktuellen — noch nicht umgesetzten — Stand gemessen)

B1a — `PreflightAssistStopTest.test_hup_during_preflight_assist_ends_the_agent_group`
(Assigment: Review Medium 1)
* Vorbedingung: unsauberes Projekt (Preflight-Befund), `VIBE_PREFLIGHT_ASSIST=1`;
  der Preflight-Agent (signalignorierender Harness mit Unter- und
  Enkelprozess) läuft; noch kein Registereintrag.
* Aktion: HUP an die Prozessgruppe der Läufersitzung.
* Erwartung: Läufer tot; Preflight-Agentengruppe samt Unter-/Enkelprozess
  tot; keine weiteren Ticks; kein Registereintrag bleibt `running`.
* Gemessen: **GRÜN** am aktuellen Stand → Verhaltens-Pin, keine Rotphase.
  Begründung: Der dem Befund zugrunde liegende Zustand („ein `EXIT`-Trap
  läuft bei Tod durch ein nicht abgefangenes Signal nicht") ist auf dieser
  Plattform nicht reproduzierbar. Empirische Gegenprobe (bash 5.3.9):
  `bash -c 'trap "…>> /tmp/opencode/traptest" EXIT; sleep 30'` + HUP →
  Exit 129 **und** Exit-Trap läuft. Damit beendet
  `trap 'stop_agent_group' EXIT` (vibe-run.sh, vor dem ersten Preflight)
  die Preflight-Agentengruppe auch bei Signaltod. Der vom Reviewer
  geforderte Fix (HUP/TERM/INT-Traps vor dem ersten Preflight) bleibt
  portabel sinnvoll; der Fall pinnt nur das beobachtbare Zielverhalten und
  verlangt keinen bestimmten Fixweg.

B1b — `EndPreflightAssistStopTest.test_hup_during_the_end_preflight_marks_the_run_ended`
(Review Medium 1, „end“-Preflight)
* Vorbedingung: Lauf registriert; Paket F1 abgeschlossen; Integrationsstand
  unsauber (end-Preflight-Assistenz fragt); Assistenzagent
  (signalignorierend) läuft.
* Aktion: HUP an die Läufersitzung.
* Erwartung: Läufer endet 129; Agentengruppe endet; Registereintrag
  `ended` mit Notiz „extern beendet (Signal HUP)“ und Exit-Code 129.
* Gemessen: **GRÜN** am aktuellen Stand → Verhaltens-Pin (die HUP/TERM/
  INT-Traps sind zum end-Preflight bereits installiert).

B2 — `StopAroundStartTest.test_repeated_hup_around_the_attempt_start_leaves_no_orphan`
(Review Medium 2)
* Vorbedingung: laufender Lauf mit signalignorierendem Harness. Das Fenster
  zwischen `) </dev/null &` und `AGENT_PID=$!` ist von außen **nicht
  zuverlässig steuerbar** (es umfasst Mikrosekunden innerhalb der Shell;
  zwischen der sichtbaren Protokollmarke „--- Versuch 1/“ und der Zuweisung
  liegen weitere Shell-Befehle, aber keine steuerbare Schwelle).
* Aktion: HUP unmittelbar nach der Versuchstart-Marke, vier Wiederholungen
  mit Verzug 0 / 20 / 50 / 200 ms (teils vor, teils nach der Zuweisung).
* Erwartung: In jeder Wiederholung enden Läufer und die gesamte
  Agentengruppe vollständig; nie eine Waise.
* Gemessen: **GRÜN** (Toleranzlauf ohne Treffer). Ein grüner Einzellauf
  schließt das Fenster nicht aus; die Wiederholungen erhöhen die
  Trefferwahrscheinlichkeit. Keine Rotphase messbar — dokumentiert, nicht
  belegt für die Fensterfreiheit.

B3a — `test_b11_stream_relay.OutputBudgetTest.test_huge_child_output_is_kept_only_as_a_tail`
(Review Medium 3, Stream-Filter)
* Vorbedingung: Hauptsession erfasst; ein Kind läuft; ein Strom wie der
  Produktionspfad (Haupt- und Kind-Ereignisse durchmischt — ein Strom mit
  ausschließlich Text einer einzigen fremden Session wäre laut
  F25-Kompatibilität ein neuer Versuch und würde die Hauptsession
  ersetzen; deshalb Durchmischung).
* Aktion: Kind-Ausgabe von rund 250 KiB (ANFANG-4711 am Anfang,
  ENDE-4711 am Ende), danach Abschluss.
* Erwartung (vereinbarte Semantik): gespeicherte Ausgabe ist ein Tail von
  höchstens 64 KiB (Anfang verworfen, Ende erhalten, laufende Einträge
  behalten den letzten Stand); Zustandsdatei < 256 KiB; `output` bleibt
  nach dem Abschluss begrenzt.
* Gemessen: **ROT** — `AssertionError: 248382 not less than or equal to
  65536 : Die gespeicherte Ausgabe ist mit 248382 Bytes unbegrenzt
  gewachsen` (ANFANG-4711 noch enthalten).

B3b — `test_b11_output_view_api.OutputBudgetTest.test_subagents_output_is_capped_to_a_small_tail`
(Review Medium 3, API)
* Vorbedingung: laufender Registereintrag; Eintrag mit rund 200 KiB
  gespeicherter Ausgabe.
* Aktion: `GET /api/subagents?name=proj`.
* Erwartung: Antwort < 8 KiB; `output` höchstens 4-KiB-Tail (ENDE-4711
  erhalten, ANFANG-4711 verworfen); `/api/subagent-output` bleibt das
  vollwertige Live-Pfadangebot (durch `SubagentOutputTest` abgedeckt).
* Gemessen: **ROT** — `AssertionError: 200022 not less than or equal to
  4096 : Das output-Feld ist mit 200022 Bytes zu groß`.

B4 — `test_b11_stream_relay.AttemptContextTest.test_attempt_pins_the_first_session_and_takes_others_as_children`
(Review Minor 2, `--attempt`-Pfad direkt getestet)
* Vorbedingung: leerer Zustand; Filter wird mit `attempt=True` aufgerufen
  (wie der Produktionspfad).
* Aktion: Strom 1 pinnt `ses_versuch_eins` und erfasst `ses_kind_a` als
  laufendes Kind; Strom 2 (neuer Aufruf, `attempt=True`) mit
  `ses_versuch_zwei`.
* Erwartung: erstes Ereignis pinnt die Hauptsession des Versuchs; das Kind
  wird erfasst; der zweite Versuch ersetzt die Hauptsession („zuletzt
  gewinnt“), ohne ein Kind zu erzeugen; das erfasste Kind bleibt.
* Gemessen: **GRÜN** am aktuellen Stand → Verhaltens-Pin (der
  attempt-Pfad ist bereits korrekt; der Review-Befund war die fehlende
  direkte Abdeckung, die dieser Fall schließt).

B5a — `test_b11_output_view_api.RunTimeFilterTest.test_unreadable_run_start_delivers_all_state_entries`
(Review Minor 4, Fall (a))
* Vorbedingung: laufender Registereintrag mit defekter `started`-Zeit;
  zwei Einträge in der Zustandsdatei.
* Aktion: `GET /api/subagents`.
* Erwartung (vereinbarte, dokumentierte fail-open-Semantik): beide
  Einträge erscheinen.
* Gemessen: **GRÜN** am aktuellen Stand → Verhaltens-Pin (fail-open ist
  bereits so umgesetzt; der Fall pinnt die vereinbarte Semantik).

B5b — `test_b11_output_view_api.RunTimeFilterTest.test_entry_with_unknown_start_stays_visible_during_a_run`
(Review Minor 4, Fall (b))
* Vorbedingung: laufender Registereintrag; Einträge mit `started` 0 und
  `started` `None` neben einem normalen Eintrag.
* Aktion: `GET /api/subagents`.
* Erwartung: alle drei Einträge bleiben sichtbar.
* Gemessen: **ROT** — `Einträge mit unbekannter Startzeit fielen aus der
  Liste: ['ses_mit_zeit']` (ses_ohne_zeit und ses_keine_zeit fehlen).

Korrekturshinweis (Transparenz): Bei der ersten Messung lief der Fall B1a
zusätzlich als ererbter Doppeltest in `EndPreflightAssistStopTest` und
scheiterte dort an der Paket-Attrappe („Der Läufer endete vor dem
Preflight-Agentenstart") — ein Erbfehler des Test-Agenten, **kein**
Rotphasen-Beleg. Behoben durch eine Fixture-Aufteilung
(`PreflightAssistFixture` als reine Hilfsklasse); die korrigierte Zählung
lautet 11 + 8 + 11 = 30 B11-Unit-Fälle (zuvor 31 gezählt).

### 7.3 Gemessene Suite-Zahlen (Runde 2, aktueller Arbeitsstand)

```
python3 -m unittest discover -s tests/unit -p 'test_b11_*.py'
→ Ran 30 tests in 32.116s, FAILED (failures=3), Exit 1
  Rot: B3a (Stream-Tail), B3b (API-Tail), B5b (Startzeit-Sichtbarkeit)
  Grün: 27 — die 8 Stamm-Stopp-Tests, die 6 Alt-Relay- und 8 Alt-API-Fälle,
        B1a, B1b, B2, B4, B5a
python3 -m unittest tests.unit.test_b11_stop_terminates_agents
→ Ran 11 tests in 25.578s, OK, Exit 0   (nach der Erbfehler-Korrektur)
PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
python3 -m unittest tests.browser.test_b11_output_ui
→ Ran 8 tests in 24.676s, OK, Exit 0    (Datei unverändert)
```

### 7.4 Regressionen

```
python3 -m unittest tests.unit.test_f25_session_continue
→ Ran 16 tests, OK, Exit 0
python3 -m unittest tests.unit.test_output_view_f19_api
→ Ran 14 tests, OK, Exit 0
python3 -m unittest tests.unit.test_b6_pi_events
→ Ran 24 tests, OK, Exit 0
```

Keine bestehenden B11-Fälle wurde abgeschwächt oder gelöscht; an
`test_b11_stop_terminates_agents.py` wurde nur der gemeinsame Helfer
`stop_and_expect_death` um den Parameter `send=True` (Vorgabe) erweitert —
alle bestehenden Aufrufe unverändert.

### 7.5 Prozess- und Verzeichnisaufräumaufwand

Beendet wurden ausschließlich vom Test-Agenten hinterlassene Restprozesse:

* `/tmp/opencode/b11tmux/parent.sh` samt `child.py` und `tee` (zwei
  Instanzen aus früheren Probeläufen) sowie der zugehörige tmux-Socket
  `tmux-1000`.
* Sechs verwaiste B11-Test-Dashboards (`bin/vibe-web.py` mit
  `VIBE=/tmp/tmp*` auf Zufalls-Ports) aus früheren API-Suitenläufen.

Die produktive Sitzung `vibe-vibe` (tmux) wurde nicht angefasst. Das
Prüfverzeichnis `/tmp/opencode/b11-redphase` samt Rohprotokollen wurde
nach der Übernahme der Auszüge in diesen Bericht entfernt.

### 7.6 Verbleibende Hinweise an Coding- und Review-Agent

1. **Medium 1 ist auf dieser Plattform nicht als Fehler reproduzierbar**
   (bash 5.3.9 führt den EXIT-Trap auch bei Signaltod aus). Der geforderte
   Fix (frühere Installation der HUP/TERM/INT-Traps) ist trotzdem portabel
   sinnvoll; B1a/B1b pin das Zielverhalten und schlagen keinen Fixweg vor.
   `docs/features/B11.md` sollte die tatsächliche Abdeckung beschreiben
   (Umsetzungssache, nicht Test).
2. **Medium 2** bleibt als Toleranzlauf dokumentiert; ein grüner Lauf ist
   kein Beweis der Fensterfreiheit.
3. Die drei roten Fälle (B3a, B3b, B5b) erwarten die vereinbarte Semantik:
   64-KiB-Tail je Eintrag in der Zustandsdatei, 4-KiB-Tail in
   `/api/subagents`, Sichtbarkeit von Einträgen mit unbekannter Startzeit
   unter aktivem Lauf.
4. `RunTimeFilterTest.corrupt_run_start` verdirbt die `started`-Zeit des
   neuesten Registereintrags in `runs.json` direkt — die Umsetzung darf
   sich nicht auf die Parsebarkeit dieser Zeits verlassen, wenn der
   Fail-open-Pfad getestet werden soll.

---

## 8. Runde 2: Rennfenster nach dem Auftragsstart (Review Medium 2, erneut beanstandet)

Anfrage des Coding-Agenten vor dem Fix: Entscheidung, ob der geplante
Fallback („`stop_agent_group` fällt bei leerem `AGENT_PID` auf die
Prozessgruppen laufender Hintergrundaufträge zurück, z. B. über `jobs -p`
unter `set -m`") deterministisch getestet werden kann.

### 8.1 Bewertung der Optionen

- **Option a (nur E2E-Toleranzlauf):** verworfen als alleiniger Nachweis.
  Das Fenster zwischen `) </dev/null &` und `AGENT_PID=$!` umfasst
  Mikrosekunden; ein Signal von außen kann das Fenster nur zufällig
  treffen. Der bestehende Toleranzfall
  (`StopAroundStartTest.test_repeated_hup_around_the_attempt_start_leaves_no_orphan`)
  bleibt unverändert als E2E-Verhaltensanker bestehen, beweist aber nie
  Fensterfreiheit.
- **Option b (fokussierter Test der Funktion in der Fehlerlage):**
  gewählt. Die Fehlerlage — Trap feuert, während der Auftrag unter aktiver
  Jobkontrolle bereits läuft und `AGENT_PID` noch leer ist — ist
  deterministisch herstellbar, weil der Test die Fensterlage selbst
  herstellt, statt zufällig hineinzutreffen. Die echte Funktion wird mit
  `extract_shell_function()` aus `bin/vibe-run.sh` extrahiert und in einer
  Hüllshell ausgeführt; eine kopierte Nachbildung würde das Verhalten nur
  behaupten. Der Signalempfang selbst (HUP an die Hüllshell) läuft über
  einen echten Trap, wie es der Läufer-Trap im Fenster tut.
- **Option c („nicht deterministisch prüfbar"):** entfällt durch Option b.

Grenze der Option b: Der Fall prüft den Vertrag von `stop_agent_group` in
der Fehlerlage, nicht die Atomität des Produktionsfensters. Wählt der
Coding-Agent stattdessen (oder zusätzlich) das Blockieren des Fensters
gegen Signale, bleibt dieser Fall als Härtetest der Funktion bestehen
(Grün), deckt die Blockierung aber nicht ab — die wäre dann erneut als
nicht-deterministisch dokumentiert und der E2E-Anker träge. Für die
Testbarkeit wird der Fallback-Weg empfohlen.

### 8.2 Neue Testfälle (vor der Implementierung geschrieben)

Klasse `StopAgentGroupFallbackTest` in
`tests/unit/test_b11_stop_terminates_agents.py`; Opferprozess ignoriert
HUP und TERM, schreibt Lebenszeichen und endet erst nach 120 s — ein Stopp
kann ihn nur über die KILL-Eskalation beenden.

1. `test_hup_trap_with_unassigned_agent_pid_kills_the_running_job`
   (AK1/No-Go, Review Medium 2) — Vorbedingung: echte
   `stop_agent_group`; `set -m` aktiv; signalignorierender Auftrag läuft
   in eigener Prozessgruppe; `AGENT_PID` ist leer; HUP-Trap ruft
   `stop_agent_group` (wie der Läufer-Trap im Fenster). Aktion: HUP an die
   Hüllshell, sobald der Auftrag läuft (Tick-Datei). Erwartung: Trap wird
   ausgeführt (`TRAP_RAN`) und die Auftragsggruppe endet vollständig.
   Fehlerfall: Auftrag überlebt als Waise.
2. `test_stop_with_unassigned_agent_pid_and_no_jobs_is_harmless` (AK1) —
   leere Kennung, keine Hintergrundaufträge; direkter Aufruf; Erwartung:
   wirkungslos, fehlerfrei, keine Selbstverletzung der Hüllshell.
3. `test_stop_with_assigned_agent_pid_kills_that_group` (AK1) —
   Normalpfad mit gesetzter Kennung; Erwartung: Gruppe endet trotz
   ignorierter Signale; schützt den Normalpfad vor Regression durch den
   Fallback.

### 8.3 Rotphasen-Protokoll (gegen den Stand vor dem Fix)

Befehl: `python3 -m unittest
tests.unit.test_b11_stop_terminates_agents.StopAgentGroupFallbackTest -v`
Exit-Code 1, 3 Fälle:

- `test_hup_trap_with_unassigned_agent_pid_kills_the_running_job` — **FAIL
  (erwartet, Rotphase):** `AssertionError: Der Auftrag (PID 94892)
  überlebt den Stopp und läuft als Waise weiter.`
- `test_stop_with_unassigned_agent_pid_and_no_jobs_is_harmless` — ok
- `test_stop_with_assigned_agent_pid_kills_that_group` — ok

Determinismusprobe des Rotfalls (3 Einzelläufe, jeweils Exit 1, gleiches
Fehlbild, Laufzeit stabil ~12 s):
`python3 -m unittest ...test_hup_trap_with_unassigned_agent_pid_kills_the_running_job`
→ RUN1/RUN2/RUN3 jeweils FAILED (failures=1).

Eine vorbereitende Ausführung lieferte zunächst einen Testfehler in der
Messmethode (Hüllshell hielt die stdout-Pipe offen, solange das Opfer im
Rot-Fall lebte); die Messung wurde entschärft (Opfer-stdout nach
/dev/null, PID-Datei fürs Aufräumen), die Assertion wurde nicht
abgeschwächt — die danach gemessene Rotphase ist die oben protokollierte.

### 8.4 Stand der B11-Stop-Suite nach den Teständerungen

Befehl: `python3 -m unittest tests.unit.test_b11_stop_terminates_agents -v`
Exit-Code 1, **14 Fälle: 13 ok, 1 FAIL** — rot ist ausschließlich
`StopAgentGroupFallbackTest.test_hup_trap_with_unassigned_agent_pid_kills_the_running_job`
(alle 13 übrigen Fälle einschließlich der beiden neuen Verankerungsfälle
grün). Nach Umsetzung des Fixes muss die volle Suite grün sein.

### 8.5 Hinweise an Coding- und Review-Agent

1. Die Tests extrahieren die Funktion über den Namen `stop_agent_group`
   und den Zeilenaufbau `name() {` … `}` aus `bin/vibe-run.sh`. Behalte
   diese Funktion als benannte Einheit; Umbenennung oder Inlining bricht
   die Extraktion absichtlich (dann ist der Testvertrag neu zu verhandeln).
2. Der Fallback darf nur die Prozessgruppen laufender Hintergrundaufträge
   dieser Shell treffen (`jobs -p`), nie die eigene Gruppe oder etwas
   Unbeteiligtes; Fall 2 pinnt die Harmlosigkeit, Fall 3 den Normalpfad.
3. `StopAroundStartTest` bleibt unverändert als E2E-Anker; der grüne
   Einzellauf beweist weiterhin keine Fensterfreiheit.
