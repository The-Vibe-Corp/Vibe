# AP19 — Testbericht des unabhängigen Test-Agenten

- Datum: 18.11.2026
- Arbeitspaket: AP19 „Session Management“ (`TICKETS.md`, Zeile 1057)
- Arbeitsbaum: `vibe-AP19-0es20i`
- Branch: `vibe/vibe-AP19-1795039154711939108-299324-2397`
- Basiscommit: `b8b08e6`
- Tester: konfigurierter Test-Agent
- Grundlage: ausschließlich Ticketwortlaut, `SPEC.md`/`AGENTS.md`, bestehende
  Nachbartests und der vorhandene Produktcode. Es existiert noch keine
  AP19-Implementierung; die Tests sind der Maßstab für deren Entwicklung.

## Auftrag und Grenzen

Auftrag war das Schreiben von Testfällen (kein Produktionscode) für AP19:

| Datei | Umfang |
|---|---|
| `tests/unit/test_ap19_sessions_registry.py` | 23 Tests (21 + 2 aus Runde 3) |
| `tests/unit/test_ap19_runner_capture.py` | 11 Tests |
| `tests/unit/test_ap19_sessions_cli.py` | 19 Tests (18 + 1 aus Runde 3, mit zwei Unterfällen) |
| `tests/unit/test_ap19_sessions_api.py` | 17 Tests |
| `tests/browser/test_ap19_sessions_ui.py` | 7 Tests |
| **Summe** | **77 Tests** |

Grenzen, die eingehalten wurden:

- Nur `tests/` und `docs/reviews/` wurden angelegt; keine Produktionsdatei,
  keine Baselines/Manifeste, keine Branches gewechselt, keine Commits.
- Nur Python-Standardbibliothek; keine echten Modellaufrufe, kein opencode,
  kein tmux gegen echte Projekte. tmux ist eine aufzeichnende Attrappe,
  Projekte liegen ausschließlich in temporären Verzeichnissen.
- Bestehende Tests wurden nur ausgeführt, nicht verändert.

## Akzeptanzkriterien (abgeleitete Zuordnung)

`TICKETS.md` nennt für AP19 keinen expliziten AK-Katalog. Die folgende
Zuordnung ist daher **eine aus dem Ticketwortlaut abgeleitete Annahme** und
wird hier offengelegt:

- **AK1 — Auflisten:** Die letzten Sessions (Standard 5, konfigurierbar)
  erscheinen mit Kennung, Zustandslabel, Agent und Projekt.
- **AK2 — Wiederfinden:** Der Zustand (insbesondere „abgebrochen“) wird aus
  dem Laufregister abgeleitet; Projekt- und Textfilter grenzen die Liste ein.
- **AK3 — Fortsetzen:** Genau eine gewählte Session wird fortgesetzt; jede
  Ablehnung (unbekannt, fremdes Projekt, aktiver Lauf, Pi) nennt einen Grund
  und startet nichts.
- **AK4 — Abbruchfestigkeit:** Die Session wird auch bei einem harten Abbruch
  des Filterprozesses dauerhaft erfasst.
- **AK5 — UI:** Eine Sessions-Karte im Projektpanel zeigt Zustand, Zeit und
  Fortsetzen; Leerzustand, Aktivsperre, Pi-Hinweis und Tastaturbedienung sind
  abgedeckt.
- **AK6 — Rückwärtskompatibilität:** Ohne die neue Option bzw. ohne
  Session-Register bleibt das bisherige Läuferverhalten unverändert.

## 1. `tests/unit/test_ap19_sessions_registry.py` — Register und Zustände

Lädt `bin/vibe_runs.py` über `SourceFileLoader` (Muster aus
`test_f25_session_continue.py`) und arbeitet ausschließlich in temporären
Laufzeitverzeichnissen.

| Test | Erwartetes Ergebnis | AK |
|---|---|---|
| `test_observe_creates_one_entry_with_all_contract_fields` | Ein Eintrag mit `session`, `project`, `name`, `run_id`, `agent`, `harness`, `first_seen`, `last_seen`; `first_seen == last_seen` beim ersten Erfassen | AK1 |
| `test_observe_updates_the_same_entry_and_keeps_first_seen` | Upsert je Kennung; `first_seen` bleibt, `last_seen` wächst | AK1 |
| `test_observe_keeps_entries_apart_per_session` | Zwei Kennungen ergeben zwei Einträge | AK1 |
| `test_observe_ignores_invalid_session_ids_and_writes_nothing` | Leere/ungültige Kennungen werden nicht geschrieben | AK1 |
| `test_observe_limits_the_register_to_the_newest_100_entries` | Höchstens 100 Einträge; die jüngsten bleiben | AK1 |
| `test_default_limit_is_five_and_an_integer` | Frisches Register liefert Limit 5 als `int` | AK1 |
| `test_set_limit_persists_and_survives_an_observe` | Gesetztes Limit bleibt nach `observe` erhalten | AK1 |
| `test_set_limit_accepts_the_boundaries_one_and_hundred` | 1 und 100 sind gültig | AK1 |
| `test_set_limit_rejects_values_outside_one_to_hundred` | 0, 101, `5.5`, `None`, `"sieben"` → `ValueError`, nichts geschrieben | AK1 |
| `test_get_returns_the_entry_or_none` | `get` liefert Eintrag bzw. `None` | AK1/AK2 |
| `test_every_run_state_maps_to_the_contract_state` | starting/running→läuft, finished→abgeschlossen, failed→fehlgeschlagen, stopped→gestoppt, paused→pausiert, blocked→blockiert, ended→abgebrochen | AK2 |
| `test_missing_or_unknown_run_id_is_unknown` | Fehlende/unbekannte Lauf-ID → `unknown`/„unbekannt“ | AK2 |
| `test_overview_entries_carry_all_contract_fields` | Übersicht trägt alle Registerfelder plus `state`/`state_label` | AK1/AK2 |
| `test_project_filter_compares_over_realpath` | Alias- und realer Pfad treffen denselben Eintrag | AK2 |
| `test_text_filter_is_case_insensitive_substring_of_the_session` | `alp` findet `SES_Alpha1` | AK2 |
| `test_text_filter_without_match_returns_an_empty_list` | Kein Treffer → leere Liste | AK2 |
| `test_default_limit_five_returns_the_five_newest_sessions` | Ohne gespeichertes Limit: die 5 jüngsten, absteigend | AK1 |
| `test_stored_limit_wins_over_the_default` | Gespeichertes Limit 3 schlägt 5 | AK1 |
| `test_parameter_limit_wins_over_the_stored_limit` | Parameter 2 schlägt gespeichertes 3 | AK1 |
| `test_parameter_limit_above_the_register_size_returns_all` | Limit 50 bei 3 Einträgen → alle 3 | AK1 |
| `test_invalid_parameter_limit_raises_value_error` | Limit 0/101 → `ValueError` | AK1 |

Fachliche Bedeutung: Das Register ist die einzige Quelle, aus der CLI, API und
UI Sessions wiederfinden. Es muss atomar, begrenzt und robust gegen ungültige
Kennungen sein; die Zustandsableitung entscheidet, ob eine Session als
„abgebrochen“ wiederherstellbar ist.

## 2. `tests/unit/test_ap19_runner_capture.py` — Erfassung im Läufer

Führt den echten `vibe_runs.py stream`-Filter als Subprozess mit
JSON-Ereignisströmen aus und prüft zusätzlich den Einbau in
`bin/vibe-run.sh` (Textvertrag) sowie einen vollständigen Attrappen-Lauf.

| Test | Erwartetes Ergebnis | AK |
|---|---|---|
| `test_main_session_is_captured_with_all_given_values` | Hauptsession wird mit Projekt, Name, Lauf-ID, Agent, Harness erfasst | AK1/AK4 |
| `test_session_run_value_is_stored_in_the_entry` | `--session-run` landet als `run_id` im Eintrag | AK1 |
| `test_without_sessions_option_nothing_is_written` | Ohne `--sessions` bleibt `sessions.json` unberührt (Bestandsverhalten) | AK6 |
| `test_child_session_events_never_create_entries` | Subagenten-Sessions erzeugen keine Registereinträge | AK1 |
| `test_pi_session_header_never_creates_an_entry` | Pi-Header werden nicht als Session erfasst | AK1 |
| `test_text_only_session_is_captured_when_promoted_at_stream_end` | Erst am Stromende erkannte Session wird nachgezogen | AK1/AK3 |
| `test_hard_aborted_stream_keeps_the_entry` | Nach `SIGKILL` des Filters bleibt der zuletzt geschriebene Eintrag erhalten | AK4 |
| `test_filter_is_configured_twice` | Zwei Filterzuweisungen: Preflight und Paketversuch | AK1 |
| `test_preflight_filter_captures_without_run_id` | Preflight-Filter erfasst ohne Lauf-ID | AK1 |
| `test_package_filter_runs_after_register_start_with_the_run_id` | Paketfilter erhält die Lauf-ID nach `register_start` | AK1 |
| `test_runner_captures_the_package_session_with_its_run_id` | Echter Läuferdurchlauf erfasst die Paketsession mit Lauf-ID | AK1/AK4 |

Fachliche Bedeutung: Sessions entstehen im Datenstrom, nicht durch
nachträgliches Raten. Gerade der harte Abbruch (AK4) ist der Fall, für den die
Wiederherstellung gebraucht wird; deshalb prüft der Test das Überleben des
Eintrags ohne sauberes Stromende.

## 3. `tests/unit/test_ap19_sessions_cli.py` — `vibe sessions`

Startet den echten CLI-Prozess (`python3 bin/vibe …`) in einem isolierten
Arbeitsbereich mit echtem Git-Projekt, Laufregister und tmux-Attrappe.

| Test | Erwartetes Ergebnis | AK |
|---|---|---|
| `test_list_shows_identifier_state_label_agent_and_project` | Liste zeigt Kennung, Zustandslabel, Agent und Projekt | AK1 |
| `test_list_default_shows_the_five_newest_sessions` | Standard 5, jüngste zuerst | AK1 |
| `test_list_limit_option_overrides_the_default` | `--limit` überschreibt den Standard | AK1 |
| `test_list_uses_the_stored_limit` | Ohne Option gilt das gespeicherte Limit | AK1 |
| `test_list_filters_by_project_name` | `--project` grenzt auf ein Projekt ein | AK2 |
| `test_list_searches_the_session_identifier_case_insensitively` | Suchtext findet ohne Groß-/Kleinschreibung | AK2 |
| `test_limit_without_value_shows_the_stored_default` | `sessions limit` zeigt den Standard | AK1 |
| `test_limit_with_value_sets_and_persists_it` | `sessions limit 3` schreibt und persistiert | AK1 |
| `test_limit_rejects_invalid_values_without_writing` | 0/101/`sieben` → Fehlermeldung, nichts geschrieben | AK1 |
| `test_resume_with_unknown_session_refuses_without_start` | Unbekannte Kennung → Ablehnung, kein Start | AK3 |
| `test_resume_with_a_session_of_another_project_refuses` | Fremdes Projekt → Ablehnung, kein Start | AK3 |
| `test_resume_with_last_starts_the_newest_session` | `--last` startet die jüngste Session | AK3 |
| `test_resume_with_aborted_picks_the_newest_aborted_session` | `--aborted` wählt die jüngste abgebrochene Session | AK3 |
| `test_resume_without_aborted_session_refuses_without_start` | Kein Treffer → Ablehnung, kein Start | AK3 |
| `test_resume_refuses_while_a_run_is_active` | Aktiver Lauf → Ablehnung, kein Start | AK3 |
| `test_resume_refuses_for_pi_with_a_clear_message` | Pi → Meldung nennt Pi und `--no-session`, kein Start | AK3 |
| `test_resume_with_session_starts_exactly_that_session` | `--session` exportiert genau diese Kennung | AK3 |
| `test_resume_refuses_for_an_unknown_project` | Unbekanntes Projekt → Ablehnung, kein Start | AK3 |

Fachliche Bedeutung: Der Vibe-Agent muss ohne UI eine abgebrochene Session
wiederfinden und exakt fortsetzen können. Jede Ablehnung muss erklären, warum
nichts gestartet wurde; stilles Scheitern wäre ein Datenverlustrisiko.

## 4. `tests/unit/test_ap19_sessions_api.py` — `GET/POST /api/sessions`

Startet den echten `vibe-web`-Server mit eigenem Port und isoliertem
HOME/VIBE-Root; Lauf- und Sessionregister werden real geschrieben, tmux ist
eine Attrappe.

| Test | Erwartetes Ergebnis | AK |
|---|---|---|
| `test_get_is_token_protected` | Ohne/falschem Token → 403 | AK1 |
| `test_unknown_project_is_rejected` | Unbekanntes Projekt → 404 | AK1 |
| `test_list_returns_all_contract_fields_and_state_labels` | Alle Vertragsfelder plus `state`/`state_label`; jüngste zuerst | AK1/AK2 |
| `test_default_limit_comes_from_the_stored_value` | Gespeichertes Limit 2 schlägt 5 | AK1 |
| `test_limit_parameter_limits_the_list` | `limit=1` liefert genau die jüngste | AK1 |
| `test_limit_parameter_is_capped_at_hundred` | `limit=500` → wirksames Limit 100 | AK1 |
| `test_text_filter_is_case_insensitive_on_the_session_id` | `text=alp` findet `ses_Alpha` | AK2 |
| `test_running_reflects_the_live_run_registry` | `running` folgt dem Live-Zustand des Laufregisters | AK3 |
| `test_resume_is_supported_for_opencode` | `resume_supported` wahr | AK3 |
| `test_resume_is_unsupported_for_pi` | `resume_supported` falsch bei Pi | AK3 |
| `test_post_is_token_protected` | Ohne Token 403, kein Start | AK3 |
| `test_unknown_session_is_refused_without_start` | Unbekannte Session → `ok:false`, kein Start | AK3 |
| `test_session_of_another_project_is_refused_without_start` | Fremdes Projekt → `ok:false`, kein Start | AK3 |
| `test_active_run_refuses_to_start_anew` | Aktiver Lauf → `ok:false`, kein Start | AK3 |
| `test_pi_refuses_with_no_session_reason` | Pi → Meldung mit „Pi“ und `--no-session` | AK3 |
| `test_unknown_action_is_refused_without_start` | Nur `action="continue"` zulässig | AK3 |
| `test_continue_starts_exactly_the_given_session` | Startbefehl enthält `VIBE_CONTINUE_SESSION=<gewählte Session>` | AK3 |

Fachliche Bedeutung: Die API ist die Brücke zwischen Sessions-Karte und
Läufer. Sie muss dieselben Limit-/Filterregeln wie die CLI anwenden und darf
eine Session niemals projektfremd oder während eines aktiven Laufs starten.

## 5. `tests/browser/test_ap19_sessions_ui.py` — Sessions-Karte

Startet das echte Dashboard; `GET/POST /api/sessions` werden im Browser
abgefangen, damit die UI unabhängig von der Serverimplementierung geprüft
wird. POSTs werden aufgezeichnet und nicht an den Server weitergereicht.

| Test | Erwartetes Ergebnis | AK |
|---|---|---|
| `test_card_lists_sessions_with_state_labels_and_pill_tones` | Karte „Sessions“ mit Kennung, Label und Tonklassen `ok`/`warn`/`bad`/`mut` | AK5 |
| `test_row_shows_a_human_readable_last_seen_time` | Lesbare Zeit statt roher Epochenwert | AK5 |
| `test_empty_state_when_no_sessions_were_captured` | „Noch keine erfassten Sessions.“ | AK5 |
| `test_resume_posts_exactly_name_session_and_action` | POST exakt `{name, session, action:"continue"}` | AK5/AK3 |
| `test_resume_is_not_offered_while_the_run_is_active` | Kein betätigbarer Fortsetzen-Knopf bei aktivem Lauf | AK5 |
| `test_pi_shows_no_resume_button_and_explains_no_session` | Kein Knopf, Hinweis mit „Pi“ und „--no-session“ | AK5 |
| `test_resume_can_be_operated_by_keyboard` | Per Tab erreichbar, Enter sendet denselben POST | AK5 |

Fachliche Bedeutung: Nach einem Abbruch muss der Nutzer die richtige Session
in der UI erkennen und ohne Kommandozeile fortsetzen können. Der exakte
Payload verhindert, dass die UI versehentlich die falsche Session startet.

## Ausführungsergebnisse (tatsächlich)

Alle Befehle im Arbeitsbaum `vibe-AP19-0es20i` (Paket-Worktree unter
`/home/nutzer/vibe-logs/worktrees/`).

### Rotphase der Unit-Suiten (Baseline ohne AP19-Implementierung)

1. `python3 -m unittest tests.unit.test_ap19_sessions_registry -v`
   → **Ran 21 tests, FAILED (errors=43)**, Exit 1.
   Schlüsselbeleg:
   `AttributeError: module 'vibe_runs_ap19_under_test' has no attribute 'SessionRegistry'`.
2. `python3 -m unittest tests.unit.test_ap19_runner_capture -v`
   → **Ran 11 tests, FAILED (failures=10)**, Exit 1.
   Schlüsselbelege:
   `Der Protokollfilter brach ab: usage: vibe_runs.py …` (unbekannte Option
   `--sessions`) und `'--sessions' not found in 'STREAM_FILTER=…'`.
   Grüner Ausnahmefall: `test_without_sessions_option_nothing_is_written`
   (AK6, Bestandsverhalten).
3. `python3 -m unittest tests.unit.test_ap19_sessions_cli -v`
   → **Ran 18 tests, FAILED (failures=21)**, Exit 1.
   Schlüsselbeleg: `vibe sessions` ist unbekannt; der Prozess gibt die
   Hilfe/Modulbeschreibung aus und führt nichts aus
   (z. B. `Ungültiges Limit '0' wurde angenommen: vibe — zentrale Steuerung …`).
4. `python3 -m unittest tests.unit.test_ap19_sessions_api -v`
   → **Ran 17 tests, FAILED (failures=11)**, Exit 1.
   Schlüsselbeleg: `404 {"ok": false, "error": {"code": "not_found", …}}` für
   `GET /api/sessions` (Route fehlt), während Token-Schutz/404-Fälle bereits
   wie erwartet greifen.

Die Rotphase ist damit für alle vier Unit-Suiten belegt: Die Fehlschläge
entstehen an der fehlenden AP19-Funktionalität, nicht an Syntax- oder
Umgebungsfehlern.

### Browser-Suite

`python3 -m unittest tests.browser.test_ap19_sessions_ui`
→ **ModuleNotFoundError: No module named 'playwright'**, Exit 1.

Playwright ist in dieser Umgebung weder installiert noch als Browser-Cache
vorhanden (`~/.cache/ms-playwright` fehlt). Die Suite ist vollständig
geschrieben und syntaktisch geprüft (`python3 -m py_compile …` → OK), ihre
Rotphase konnte hier aber **nicht** gezeigt werden. Das ist ein
Umgebungsbefund, kein Testergebnis zur UI.

### Regressionen (nur ausgeführt, nicht verändert)

`python3 -m unittest tests.unit.test_ap14_runner_continue tests.unit.test_ap14_output_view_api tests.unit.test_f25_session_continue tests.unit.test_output_view_f19_api`
→ **Ran 53 tests, OK**, Exit 0 (~28 s).

Damit bleiben die bestehende Continue-Mechanik, die Live-Ausgabe-API, die
F25-Sessionfortsetzung und die F19-Ausgabe-API unberührt.

## Hervorgehobene Annahmen

Diese Punkte sind nicht explizit im Ticket festgelegt. Die Tests definieren
sie als Vertrag; die Implementierung muss sie erfüllen oder der Vertrag muss
gemeinsam angepasst werden:

1. **API-Namen des Registers:** `SessionRegistry(runtime)` mit
   `.all()`, `.get()`, `.observe(session, project, name, run_id, agent,
   harness, now=None)`, `.limit()`, `.set_limit(n)` sowie
   `session_overview(runtime, project=None, limit=None, text=None)`.
2. **Erstes Erfassen:** `first_seen == last_seen` beim ersten `observe`.
3. **Reihenfolge:** Übersicht sortiert nach `last_seen` absteigend.
4. **Projektfilter:** vergleicht über `os.path.realpath`, sodass Alias- und
   realer Pfad denselben Eintrag treffen.
5. **HTTP-Vertrag:** `GET /api/sessions` liefert `ok`, `running`,
   `resume_supported`, `limit`, `sessions`; `POST /api/sessions` akzeptiert
   exakt `{name, session, action:"continue"}` und nur diese Aktion.
6. **UI-Vertrag:** Karte „Sessions“ im Bereich `[data-panel='arbeit']`,
   Zeilen mit `data-session`, Pille `span.pill` mit den Tonklassen
   `run`/`ok`/`warn`/`bad`/`mut`, Knopftext „Fortsetzen“, Leertext
   „Noch keine erfassten Sessions.“, Pi-Hinweis mit „--no-session“.
7. **Zeitdarstellung:** Die Zeile zeigt eine lesbare Zeit (Datum `TT.MM.JJJJ`
   oder Uhrzeit `HH:MM`), nicht den rohen `last_seen`-Wert.
8. **Browser-Rotphase:** konnte wegen fehlendem Playwright nicht
   nachgewiesen werden (siehe oben).

## Grenzen der Testfälle

- Es werden keine echten Modellaufrufe ausgeführt; opencode/tmux sind
  Attrappen. Ein Echtheitsnachweis gegen einen realen opencode-Server ist
  nicht Teil dieser Abnahme.
- Die Browser-Suite wurde hier nicht ausgeführt; ihre Fähigkeit, echte
  DOM-/Fokusprobleme zu finden, ist damit ungeprüft.
- Ein defektes `sessions.json` (Syntaxfehler, falsche Typen) ist bewusst nicht
  getestet, weil das Ticket dazu kein Verhalten festlegt. Eine spätere
  Entscheidung (tolerieren vs. melden) muss den Vertrag ergänzen.
- Nebenläufigkeit (zwei Prozesse schreiben gleichzeitig ins Register) wird nur
  indirekt über die vorhandene Sperrdatei-Konvention adressiert, nicht mit
  einem parallelen Stresstest.
- Die UI-Prüfung deckt Desktop 1400×900 ab; keine Responsive-/Touch-Prüfung.

## Fazit

74 Testfälle bilden Auflisten, Wiederfinden, Fortsetzen, Abbruchfestigkeit,
UI und Rückwärtskompatibilität ab. Die vier Unit-Suiten sind am Basiscommit
nachweislich rot; die Regressionen bleiben mit 53 Tests grün. Die
Browser-Suite ist geschrieben, konnte in dieser Umgebung aber nicht ausgeführt
werden. Es wurden keine Produktionsdateien verändert und keine Commits
erstellt.

## Nachträge Runde 2 (2026-11-18)

Nach der AP19-Implementierung liefen 72 von 74 Fällen grün. Die zwei übrigen
Fehlschläge waren Konstruktionsfehler in den Tests selbst, nicht in der
Implementierung. Beide Methoden in `tests/unit/test_ap19_sessions_registry.py`
wurden korrigiert; die fachlichen Erwartungen blieben unverändert und wurden
nicht abgeschwächt.

### Befund 1 — `ObserveTest.test_observe_creates_one_entry_with_all_contract_fields`

- Ursache: `assertEqual(ist, soll, eintrag, meldung)` übergab vier
  Positionsargumente; `unittest.TestCase.assertEqual` akzeptiert höchstens
  drei (`TypeError: … takes from 3 to 4 positional arguments but 5 were
  given`). Der Fehler trat unabhängig von der Implementierung auf.
- Korrektur: Meldung als `msg=` benannt und den Eintrag zur Diagnose in die
  Meldung aufgenommen:
  `self.assertEqual(entry.get("first_seen"), entry.get("last_seen"),
  msg="Beim ersten Sehen müssen first_seen und last_seen gleich sein: " +
  repr(entry))`.
- Erwartung unverändert: Beim ersten Erfassen sind `first_seen` und
  `last_seen` gleich.

### Befund 2 — `ObserveTest.test_observe_ignores_invalid_session_ids_and_writes_nothing`

- Ursache: Das Meldungsargument wurde eager ausgewertet. Wenn die Datei
  korrekt **nicht** existierte (der Fachwunsch), warf
  `self.sessions_file().read_text(...)` bereits `FileNotFoundError`, bevor
  `assertFalse` die wahre Aussage prüfen konnte.
- Korrektur: Zuerst `written = self.sessions_file().exists()` ermitteln, dann
  `assertFalse(written, …)`; der Dateiinhalt wird nur gelesen, wenn `written`
  wahr ist.
- Erwartung unverändert: Ungültige Kennungen schreiben keine
  `sessions.json` und erscheinen nie im Register oder in der Auflistung.

### Erneute echte Läufe

1. `python3 -m unittest tests.unit.test_ap19_sessions_registry -v`
   → **Ran 21 tests, OK**, Exit 0.
2. `python3 -m unittest tests.unit.test_ap19_runner_capture -v`
   → **Ran 11 tests, OK**, Exit 0.
3. `python3 -m unittest tests.unit.test_ap19_sessions_cli -v`
   → **Ran 18 tests, OK**, Exit 0.
4. `python3 -m unittest tests.unit.test_ap19_sessions_api -v`
   → **Ran 17 tests, OK**, Exit 0.
5. `python3 -m unittest tests.browser.test_ap19_sessions_ui`
   → **Ran 7 tests, OK**, Exit 0. Playwright ist inzwischen verfügbar; der
   Umgebungsbefund aus Runde 1 („nicht ausführbar“) ist damit überholt.
6. Regressionen:
   `python3 -m unittest tests.unit.test_ap14_runner_continue tests.unit.test_ap14_output_view_api tests.unit.test_f25_session_continue tests.unit.test_output_view_f19_api`
   → **Ran 53 tests, OK**, Exit 0.

Damit sind alle 74 AP19-Fälle und alle 53 Regressionstests grün. Es wurden
keine weiteren Dateien und keine Produktionsdateien verändert sowie keine
Commits erstellt.

## Nachträge Runde 3 (2026-11-19)

Grundlage: Review-Befunde M1 (Projektfilter/CWD), M2 (Kürzen nach
Einfügereihenfolge), Minor (`session_overview` bei beschädigtem `last_seen`)
sowie H1 (fehlende Browser-Rotphasen-Dokumentation). Es wurden **nur
Testfälle ergänzt**; bestehende Fälle, Produktionsdateien und Branches blieben
unangetastet. Die zugehörigen Implementierungskorrekturen (M1/M2/Minor/Toast)
sind **nicht** Teil dieser Runde; die drei neuen Fälle sind gegen `57cc5db`
erwartungsgemäß **ROT**.

Neue Fallzahl: **77** (23 Registry + 11 Capture + 19 CLI + 17 API + 7 Browser).
Der CLI-Fall enthält zwei Unterfälle (`subTest`), zählt aber als ein Testfall.

### A1 (Review M1) — `ProjectFilterCwdTest` in `tests/unit/test_ap19_sessions_cli.py`

Fachlichkeit: `--project` ist ein Projektname aus der Projektkarte. Die
Auflösung darf nicht davon abhängen, aus welchem Arbeitsverzeichnis die CLI
läuft; ein unbekannter Name ist ein Fehler, keine stille Leerliste.

`test_list_project_filter_works_from_a_foreign_cwd` (zwei Unterfälle):
- Vorbedingung: Projekt `proj` mit erfasster Session; CWD ist ein leeres
  Fremdverzeichnis unterhalb von `TMPDIR`, nicht die Workspace-Wurzel.
- (a) Erwartung: `vibe sessions list --project proj` zeigt `ses_proj`,
  Exit 0.
- (b) Erwartung: `--project gibtesnicht` endet mit Exit != 0, nennt den Namen
  und erzeugt keinen Traceback.
- Rotphase gegen `57cc5db`:
  `python3 -m unittest tests.unit.test_ap19_sessions_cli.ProjectFilterCwdTest -v`
  → **Ran 1 test, FAILED (failures=2)**, Exit 1.
  - (a) `AssertionError: 'ses_proj' not found in 'Keine Sessions im Register.\n'`
  - (b) `AssertionError: 0 == 0 : Unbekanntes Projekt wurde still als leere
    Liste behandelt: Keine Sessions im Register.`

### A2 (Review M2) — `OverviewLimitTest.test_reobserved_old_entry_survives_the_100_limit_trim`

Fachlichkeit: Die Obergrenze 100 muss nach `last_seen` verwerfen. Ein erneut
beobachteter alter Eintrag trägt das neueste `last_seen` und ist damit
fortsetzbar; er darf nicht wegen seiner alten Einfügeposition wegfallen.

- Vorbedingung: `ses_001`..`ses_100` mit `last_seen` 1..100 beobachten;
  danach `ses_001` mit `now=200` erneut beobachten und `ses_neu` mit
  `now=201` (erzwingt das Kürzen).
- Erwartung: `ses_001` bleibt, `ses_002` (kleinstes `last_seen`) fällt weg,
  genau 100 Einträge, Übersicht beginnt mit `ses_neu`, `ses_001`, `ses_100`.
- Rotphase gegen `57cc5db`:
  `python3 -m unittest tests.unit.test_ap19_sessions_registry.OverviewLimitTest.test_reobserved_old_entry_survives_the_100_limit_trim -v`
  → **FAILED (failures=1)**, Exit 1.
  Kernaussage:
  `AssertionError: 'ses_001' not found in ['ses_002', …, 'ses_100', 'ses_neu']
  : Der erneut gesehene Eintrag wurde nach Einfügereihenfolge verworfen`.

### A3 (Review Minor) — `OverviewRobustnessTest.test_overview_skips_entries_with_corrupt_last_seen`

Fachlichkeit: Ein einzelner manuell beschädigter Eintrag (`last_seen` als
Text) darf Liste, API und UI nicht mit `ValueError` abbrechen.

- Festgelegte Variante: Der beschädigte Eintrag wird **übersprungen** (nicht
  mit `last_seen` 0 geführt).
- Vorbedingung: `sessions.json` von Hand mit zwei Einträgen — `ses_ok` mit
  intakten Zahlenfeldern, `ses_bad` mit `"last_seen": "abc"`.
- Erwartung: kein Absturz; die Übersicht enthält nur `ses_ok`.
- Rotphase gegen `57cc5db`:
  `python3 -m unittest tests.unit.test_ap19_sessions_registry.OverviewRobustnessTest.test_overview_skips_entries_with_corrupt_last_seen -v`
  → **FAILED (errors=1)**, Exit 1.
  Kernaussage: `ValueError: invalid literal for int() with base 10: 'abc'`.

### B (Review H1) — Browser-Rotphase gegen den Basiscommit

Reproduktion am Basiscommit `b8b08e6` in einem temporären, losgelösten
Worktree; der Hauptarbeitsbaum blieb auf `57cc5db`.

1. `git worktree add --detach /tmp/opencode/ap19-rot-b8b08e6 b8b08e6`
   → Exit 0, `HEAD is now at b8b08e6`.
2. Fünf AP19-Testdateien unverändert aus `57cc5db` kopiert:
   `git show 57cc5db:<pfad> > /tmp/opencode/ap19-rot-b8b08e6/<pfad>`
   (Registry, Runner-Capture, CLI, API, Browser).
3. Im Rot-Worktree:
   `python3 -m unittest tests.browser.test_ap19_sessions_ui -v`
   → **Ran 7 tests in 145.278s, FAILED (errors=7)**, Exit 1.
   Alle sieben Fälle scheitern identisch beim Warten auf die Sessions-Karte:
   `playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 20000ms
   exceeded.` Betroffen: `test_card_lists_sessions_with_state_labels_and_pill_tones`,
   `test_row_shows_a_human_readable_last_seen_time`,
   `test_empty_state_when_no_sessions_were_captured`,
   `test_resume_posts_exactly_name_session_and_action`,
   `test_resume_is_not_offered_while_the_run_is_active`,
   `test_pi_shows_no_resume_button_and_explains_no_session`,
   `test_resume_can_be_operated_by_keyboard`.
4. Aufgeräumt:
   `git worktree remove --force /tmp/opencode/ap19-rot-b8b08e6`
   → Exit 0, Verzeichnis entfernt; `git worktree list` zeigt nur die bekannten
   Worktrees (Hauptprojekt, AP19-Arbeitsbaum, F31-Arbeitsbaum).

Hinweis: Die erste Ausführung derselben Suite gegen den unveränderten
Basisstand erfolgte bereits am 18.11.2026 durch den Koordinator
(`Ran 7 tests in 143.694s, FAILED (errors=7)`). Die obige Reproduktion
bestätigt dieses Ergebnis und macht es nachvollziehbar.

### Erneute Läufe am Paketstand `57cc5db` (nach Ergänzung)

- `python3 -m unittest tests.unit.test_ap19_sessions_registry -v`
  → **Ran 23 tests, FAILED (failures=1, errors=1)**, Exit 1 — genau A2/A3 rot,
  die 21 Bestandsfälle grün.
- `python3 -m unittest tests.unit.test_ap19_sessions_cli -v`
  → **Ran 19 tests, FAILED (failures=2)**, Exit 1 — die zwei Unterfälle aus A1
  rot, die 18 Bestandsfälle grün.
- `python3 -m unittest tests.unit.test_ap19_runner_capture tests.unit.test_ap19_sessions_api -v`
  → **Ran 28 tests, OK**, Exit 0.
- `python3 -m unittest tests.browser.test_ap19_sessions_ui`
  → **Ran 7 tests, OK**, Exit 0.
- Regressionen (AP14/F25/F19):
  `python3 -m unittest tests.unit.test_ap14_runner_continue tests.unit.test_ap14_output_view_api tests.unit.test_f25_session_continue tests.unit.test_output_view_f19_api`
  → **Ran 53 tests, OK**, Exit 0.

Damit sind 74 der 77 AP19-Fälle grün; die drei neuen Fälle sind bis zur
Umsetzung der Review-Korrekturen erwartungsgemäß rot. Es wurden keine
Produktionsdateien verändert und keine Commits erstellt.

### Home-Pfad-Hygiene (Befund aus der Vollprüfung)

Die Hygiene-Prüfungen des Projekts
(`tests/unit/test_ap12_github_readiness.py` und `tests/unit/test_release.py`)
lehnen versionierte Dateien mit absoluten echten Home-Pfaden ab. Der Bericht
enthielt eine solche Stelle im Abschnitt „Ausführungsergebnisse“ (Zeile 199):
einen absoluten Pfad mit echtem Nutzer-Home-Präfix auf den Arbeitsbaum
`vibe-AP19-0es20i`.

Ersetzt nach der etablierten AP17-Konvention:
- vorher: absoluter Pfad `$HOME/vibe-logs/worktrees/vibe-AP19-0es20i` mit
  echtem Home-Präfix
- nachher: „Alle Befehle im Arbeitsbaum `vibe-AP19-0es20i` (Paket-Worktree
  unter `/home/nutzer/vibe-logs/worktrees/`).“

Die anschließende Suche `grep -n "/home/" docs/reviews/AP19-test-agent-report.md`
findet nur noch die Konventionsform `/home/nutzer/vibe-logs/worktrees/`; echte
Nutzer-Home-Pfade sind nicht mehr enthalten (`/tmp/opencode`-Pfade sind
zulässig und bleiben).

Beide Hygiene-Fälle wurden einzeln ausgeführt:
- `python3 -m unittest tests.unit.test_ap12_github_readiness.TrackedContentHygieneTest.test_no_tracked_file_contains_personal_home_paths_or_secrets -v`
  → **Ran 1 test, OK**, Exit 0.
- `python3 -m unittest tests.unit.test_release.ReleaseBuildTest.test_repository_content_has_no_personal_home_paths_or_secrets -v`
  → **Ran 1 test, OK**, Exit 0.

Die übrigen vorbestehenden Befunde dieser Suiten sind nicht Teil dieses
Nachtrags.

### Minor aus Review Runde 2 — boolescher `last_seen`

Der Robustheitsfall `OverviewRobustnessTest.test_overview_skips_entries_with_corrupt_last_seen`
wurde um einen booleschen Unterfall erweitert (kein neuer Testfall, damit
bleibt die Summe bei 77): Neben `"last_seen": "abc"` wird nun auch
`"last_seen": true` geprüft. Beide Varianten müssen wie jeder unlesbare
Zeitwert übersprungen werden; ein boolescher Wert darf nicht als Zeit 1
missverstanden und mitgelistet werden. Die bestehende Erwartung
(`["ses_ok"]`) blieb unverändert und wurde nicht abgeschwächt.

Rotphase am Stand `b5ee2cd`:
`python3 -m unittest tests.unit.test_ap19_sessions_registry.OverviewRobustnessTest.test_overview_skips_entries_with_corrupt_last_seen -v`
→ **Ran 1 test, FAILED (failures=1)**, Exit 1; nur der Unterfall
`last_seen='bool'` scheitert:
`AssertionError: Lists differ: ['ses_ok'] != ['ses_ok', 'ses_bad']` — der
boolesche Eintrag erscheint mit `'last_seen': 1`. Der Text-Unterfall
(`"abc"`) ist bereits grün.

Die Korrektur (`bool` in `_epoch_number` als unlesbar behandeln) ist Teil der
Implementierungsrunde, nicht dieses Test-Nachtrags; nach ihr muss derselbe
Fall grün laufen. Es wurden keine Produktionsdateien verändert und keine
Commits erstellt.
