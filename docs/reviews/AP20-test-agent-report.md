# AP20 – Test-Agent-Bericht (unabhängige Browser-Abnahme)

- **Arbeitspaket:** AP20 „UI Verbesserungen Ausgabe“ (TICKETS.md, Screenshot
  `/tmp/opencode/vibe_ui.png`)
- **Worktree:** `/home/nutzer/vibe-logs/worktrees/vibe-AP20-yBZNBt`
- **Branch:** `feature/m0p/ap20-2`, Basis `20d1719`
- **Rolle:** unabhängiger Test-Agent (TDD-Rotphase und Review-Nachbesserung)
- **Datum:** 2026-11-19
- **Status:** Suite nach Review auf 12 Fälle erweitert; aktueller Arbeitsbaum
  grün (12/12). Rotnachweise für die Reviewbefunde sind als Rohausgabe
  dokumentiert (Abschnitt 6).

## 1. Auftrag und Abgrenzung

Angelegt bzw. geändert wurden ausschließlich:

1. `tests/browser/test_ap20_output_overview_ui.py` – unabhängige
   Browser-Abnahmesuite (jetzt 12 Testfälle).
2. `docs/reviews/AP20-test-agent-report.md` – dieser Bericht.

Nicht verändert: Produktionsdateien (`bin/*`, `bin/web/styles.css`,
`bin/web/app.js`), gemeinsame Dokumentation (`TICKETS.md`,
`docs/features/*`, `docs/baseline.md`, `docs/reviews/AP20-review-*.md`),
andere Worktrees. Keine Commits, kein Branchwechsel.

Die Suite ist aus der Abnahme formuliert, nicht aus der bestehenden
Implementierung. Die Erwartungen an den Neuaufbau:

| Punkt | Inhalt |
|---|---|
| 1 | B11/F30-Vertrag bleibt (Panel, Agentenansichten, Zielauswahl, Karten, Vergrößerung, Highlighter, kein Modal/Tablist) |
| 2 | Kompakte Übersicht `[data-panel='ausgabe'] .bv-overview[aria-label='Aktive Agenten'][data-active-agents='6']` mit Zählertext, Zeilen `.bv-overview-row[data-overview-session=…]`, Status-Pille, Fokus-Knopf `button[data-focus-session=…][aria-label*='fokussieren']` |
| 3 | Höchstens ein Scrollbereich je Modus: `.bv-subs` ohne horizontalen Overflow (1400 px und 900 px), jedes `.bv-log` im Normalmodus `overflow-y: hidden`, ≤ 1 tatsächlich scrollbarer Bereich (panelweit), kein horizontaler Scrollbereich |
| 4 | Umbrechendes Raster: 6 Karten in ≥ 2 Zeilen, rechte Kante ≤ Panel rechts + 2 |
| 5 | Fokus-Modus: genau eine Ansicht `enlarged` (≥ 70 % vh / ≥ 60 % vw), deren `.bv-log` `overflow-y: auto` und einziger Scrollbereich, Live-Ausgabe läuft weiter, Escape **und** zweiter Klick stellen zurück; Übersichts-, Karten- und Haupt-Fokus-Knopf teilen den Zustand; `aria-expanded` folgt an Knopf und Übersichtszeile |
| 6 | Bestehende Suiten bleiben unverändert grün (nicht Teil dieser Suite) |

## 2. Testfälle (12)

| # | Testfall | AK (Ticket-Ziel) | Prüft |
|---|---|---|---|
| 1 | `test_b11_f30_contract_remains_with_six_subagents` | 1 | Panel; Hauptagent + 6 Subagenten gleichzeitig im DOM und sichtbar, `role=log`; 7 Optionen in `select[aria-label='Ziel']`; `textarea[aria-label*='Zusatzanweisung']`; Senden-Knopf; `hl-*`-Spans und wörtlicher Text; `.bv-subs`; Karten ≥ 300 px; Vergrößern-Knopf je Karte; kein Modal, keine Tablist; „Fortsetzen“ bei gestopptem Lauf |
| 2 | `test_overview_lists_all_agents_with_compact_rows` | 2 | Übersicht vorhanden/sichtbar, `data-active-agents='6'`, Zählertext mit „6“, 7 Zeilen (Hauptsession + 6 Subagenten), Agentenname, gekürzte Beschreibung, Status-Pille, Fokus-Knopf je Subagent, Zeilenhöhe ≤ 90 px |
| 3 | `test_normal_mode_has_no_nested_scrollbars_at_1400` | 3 | `.bv-subs` `scrollWidth <= clientWidth + 2`; alle `.bv-log` `overflow-y: hidden`; ≤ 1 scrollbarer Bereich und dieser panelweit; keine horizontalen Scroller |
| 4 | `test_narrow_viewport_has_no_horizontal_overflow_at_900` | 3 | gleiche Messung bei Viewport 900×900 |
| 5 | `test_subagent_cards_wrap_into_rows_within_the_panel` | 4 | 6 Karten in ≥ 2 Zeilen (distinkte `y`), ≥ 2 Spalten, rechte Kante ≤ Panel rechts + 2 |
| 6 | `test_overview_focus_enlarges_one_card_and_unlocks_scroll` | 5 | Fokus per Übersichts-Knopf: nur Karte A `enlarged`, ≥ 70 % vh / ≥ 60 % vw, `.bv-log` `overflow-y: auto`, genau 1 scrollbarer Bereich (Karte A), Live-Marker erscheint nach Überschreiben der Zustandsdatei, **Escape ohne Ersatzweg** stellt Normalgröße + `overflow-y: hidden` her; `aria-expanded` an Karten- und Übersichts-Knopf `true` → `false` |
| 7 | `test_second_focus_click_restores_normal_mode` | 5 | Fokus per Übersichts-Knopf, dann derselbe Knopf ein zweites Mal (ohne Escape): Normalgröße, `overflow-y: hidden`, `aria-expanded` wieder `false`, ≤ 1 Scrollbereich |
| 8 | `test_card_button_and_overview_focus_share_the_same_state` | 5 | Karten-Vergrößern-Knopf → Übersichts-Fokus-Knopf hebt auf; Übersichts-Fokus → Karten-Knopf „Verkleinern“ hebt auf; `aria-expanded` an beiden Knöpfen folgt jedem Wechsel |
| 9 | `test_main_agent_header_focus_button_enlarges_main_view` | 5 | `button[data-focus-session][aria-label*='fokussieren']` im Kopf von `[data-agent-view][data-role='main']`: Klick vergrößert die Hauptansicht (≥ 70 % vh / ≥ 60 % vw), deren langes `.bv-log` `overflow-y: auto` und einziger Scrollbereich; Escape und zweiter Klick stellen zurück; `aria-expanded` an Haupt-Knopf **und** Haupt-Übersichtszeile `true`/`false` |
| 10 | `test_session_switch_with_active_focus_keeps_no_orphan_state` | 6 | Fokus auf Subagent A, dann Hauptsession in der Zustandsdatei auf `NEW_MAIN_SESSION`: keine vergrößerte alte Hauptansicht, kein verwaister Fokus, genau ein Scrollbereich (Karte A), Übersichtszeile der Hauptsession folgt der neuen Kennung, alte Zeile verschwindet, `aria-expanded` konsistent |
| 11 | `test_zero_running_subagents_shows_empty_overview` | 2/3 | Zustandsdatei ohne Subagenten: `.bv-overview[data-active-agents='0']` mit sichtbarem Leerzustandstext, `.bv-subs` ausgeblendet, nur Hauptansicht, ≤ 1 Scrollbereich, keine JS-Fehler |
| 12 | `test_finished_subagent_leaves_overview_and_view` | 2 | `completed`-Subagent A verschwindet aus Ansicht **und** Übersicht, `data-active-agents` wird „5“, Haupt + 5 bleiben |

Fachliche Bedeutung je Fall steht ausführlich im Modul-Docstring der Suite
(Vorbedingung, Aktion, Erwartung, Fehlerfall).

### Messhelfer (robust gegen DOM-Umbauten)

- `OVERVIEW_JS` liest Übersicht, Zähler, Zeilen, Status-Pille, Fokus-Knopf
  und Sichtbarkeit ohne Annahmen über die interne Verschachtelung.
- `LAYOUT_JS` misst alle Nachfahren des Panels: tatsächlich scrollbare
  Bereiche (`overflow-y` `auto`/`scroll` **und** `scrollHeight >
  clientHeight`), horizontale Scroller (`overflow-x` `auto`/`scroll` **und**
  `scrollWidth > clientWidth + 2`), `panelWide` (enthält alle
  `[data-agent-view]`), `.bv-subs`-Maße sowie `overflow-y` jedes `.bv-log`.
- `DESCRIPTION_TRUNCATION_JS` akzeptiert beide zulässigen Kürzungsarten:
  gekürzter Text oder visuelles Clipping (`text-overflow: ellipsis`,
  `overflow: hidden` mit tatsächlichem Überlauf). Es wird keine bestimmte
  CSS-Technik erzwungen.
- `wait_main_enlarged`/`wait_main_normal` prüfen die Hauptansicht mit
  denselben Schwellen wie die Karten (≥ 70 % vh / ≥ 60 % vw).
- `long_main_log()` liefert genug Hauptlog-Zeilen, damit die vergrößerte
  Hauptansicht tatsächlich scrollt; sonst wäre „einziger Scrollbereich“
  nicht aussagekräftig.

## 3. Review-Nachbesserungen (Runde 1)

| Reviewbefund | Umsetzung im Test |
|---|---|
| M2: Escape-Pfad durch `except AssertionError` + Ersatz-Klick maskiert | Fallback vollständig entfernt. Test 6 verlangt nach `page.keyboard.press("Escape")` zwingend `wait_normal(target, timeout=8)`. Ein fehlender Escape-Handler macht den Test rot (Mutationsnachweis Abschnitt 6.3). |
| M2: zweiter-Klick-Pfad nicht eigenständig | Neuer Test 7 `test_second_focus_click_restores_normal_mode` ohne Escape. |
| Medium: Haupt-Fokus-Knopf ohne Klick-Handler | Neuer Test 9 prüft den Knopf im Hauptkopf inklusive `enlarged`, Größe, Scrollbereich, Restzustand und `aria-expanded` an Knopf und Haupt-Übersichtszeile. Der Test wird ohne Handler rot (Mutationsnachweis Abschnitt 6.2). |
| Minor: Sessionwechsel bei aktivem Fokus ungetestet | Neuer Test 10 wechselt die Hauptsession in der Zustandsdatei und prüft verwaisten Fokus, Scrollbereiche und die neue Übersichtszeile. |
| Minor: Null-Subagenten-Zustand ungetestet | Neuer Test 11 prüft `data-active-agents='0'`, sichtbaren Leerzustand, ausgeblendetes `.bv-subs`, Scrollbereiche und JS-Fehler. |
| `aria-expanded` in der Suite nicht abgedeckt | Tests 6, 8 und 9 prüfen `aria-expanded` an Übersichts-Fokus-Knopf, Karten-Knopf und Haupt-Knopf jeweils im Aus- und Eingangszustand (mindestens `true` → `false`). |

## 4. Testumgebung

- Echtes Dashboard `bin/vibe-web.py`, eigener freier Port, isoliertes
  VIBE-Root (`tempfile.TemporaryDirectory`), eigener `VIBE_STATE`,
  `VIBE_RUNTIME`, `HOME`, `TMPDIR`, `TMUX_TMPDIR`.
- Lokale opencode-Attrappe (`ThreadingHTTPServer`) liefert für
  `/message` eine leere Nachrichtenliste. Damit greift der dokumentierte
  State-Fallback: Ausgabe aus `proj.log.state.json`, Live-Verlängerung durch
  Überschreiben dieser Datei (kein echter Modellaufruf).
- Lauf und Subagenten über das echte Laufregister (`bin/vibe_runs.py start`).
- Playwright/Chromium vorhanden (`~/.cache/ms-playwright/chromium-1255`).
- Viewports: 1400×900 (Standard), 900×900 (Fall 4).

## 5. Rotphase gegen den Basisstand `20d1719` (unverändert)

Der ursprüngliche Basisstand ohne AP20-Implementierung wurde mit der
damaligen 8-Fall-Suite geprüft:

```bash
BASE=/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap20-red-<pid>
git -C /home/nutzer/vibe-logs/worktrees/vibe-AP20-yBZNBt archive 20d1719 | tar -x -C "$BASE"
cp tests/browser/test_ap20_output_overview_ui.py "$BASE/tests/browser/"
cd "$BASE" && python3 -m unittest tests.browser.test_ap20_output_overview_ui -v
```

Ergebnis (zweimal reproduziert):

```
Ran 8 tests in 95.031s
FAILED (failures=7)
```

Konkrete Fehlschläge (Auszug der Assertion-Meldungen):

| Testfall | Meldung |
|---|---|
| `..._overview_lists_all_agents_with_compact_rows` | `AssertionError: Kompakte Übersicht (data-active-agents='6') fehlt oder ist unvollständig: {'panel': True, 'present': False}` |
| `..._finished_subagent_leaves_overview_and_view` | `AssertionError: Kompakte Übersicht (data-active-agents='6') fehlt oder ist unvollständig: {'panel': True, 'present': False}` |
| `..._overview_focus_enlarges_one_card_and_unlocks_scroll` | `AssertionError: Kompakte Übersicht (data-active-agents='6') fehlt oder ist unvollständig: {'panel': True, 'present': False}` |
| `..._card_button_and_overview_focus_share_the_same_state` | `AssertionError: Kompakte Übersicht (data-active-agents='6') fehlt oder ist unvollständig: {'panel': True, 'present': False}` |
| `test_normal_mode_has_no_nested_scrollbars_at_1400` | `AssertionError: 3400 not less than or equal to 1266 : .bv-subs hat horizontalen Overflow: scrollWidth=3400 px, clientWidth=1264 px` |
| `test_narrow_viewport_has_no_horizontal_overflow_at_900` | `AssertionError: 4187 not less than or equal to 866 : .bv-subs hat bei 900 px horizontalen Overflow: scrollWidth=4187 px, clientWidth=864 px` |
| `test_subagent_cards_wrap_into_rows_within_the_panel` | `AssertionError: 1764 not less than or equal to 1334 : Karte ses_ap20_c ragt über den Panelrand hinaus: rechte Kante 1764.0 px, Panel rechts 1332.0 px` |

Der einzige grüne Fall im Basisstand ist der Regression-Schutz
`test_b11_f30_contract_remains_with_six_subagents`.

## 6. Rotnachweise der Review-Nachbesserungen

### 6.1 Erster Lauf der erweiterten Suite gegen den Arbeitsbaum

Zum Zeitpunkt dieses Laufs war der Haupt-Fokus-Handler bereits durch den
parallel arbeitenden coding-agent ergänzt; der Null-Subagenten-Leerzustand
war noch fehlerhaft. Rohausgabe:

```
test_zero_running_subagents_shows_empty_overview ... FAIL
...
  File ".../test_ap20_output_overview_ui.py", line 1613, in test_zero_running_subagents_shows_empty_overview
    self.assertTrue(
AssertionError: False is not true : Der Leerzustand der Übersicht ist ohne Subagenten nicht sichtbar

Ran 12 tests in 28.446s
FAILED (failures=1)
```

Damit war belegt: `overviewEmpty` wurde bei vorhandener Hauptzeile
ausgeblendet (`overviewEmpty.hidden=entries.length>0`), obwohl ohne
Subagenten ein sichtbarer Leerzustand gefordert ist.

### 6.2 Mutationsnachweis Haupt-Fokus-Knopf

Weil der coding-agent den fehlenden Klick-Handler während der
Nachbesserung bereits ergänzt hatte, wurde die Wirksamkeit von Test 9
zusätzlich in einer temporären Kopie außerhalb des Arbeitsbaums belegt:
Dort wurde ausschließlich die Zeile
`mainToggle.addEventListener('click',…)` entfernt, die Produktionsdatei im
Arbeitsbaum blieb unberührt.

```
test_main_agent_header_focus_button_enlarges_main_view ... FAIL
...
  File ".../test_ap20_output_overview_ui.py", line 1415, in test_main_agent_header_focus_button_enlarges_main_view
    self.wait_main_enlarged()
...
AssertionError: Die Hauptagentenansicht wurde nicht ansichtsfüllend vergrößert: class='bv-view bv-main' box={'x': 68, 'y': 526.453125, 'width': 1264, 'height': 360}

Ran 1 test in 12.042s
FAILED (failures=1)
```

Der Test ist damit nachweislich in der Lage, den ursprünglichen Bug
(„Haupt-Fokus-Knopf ohne Funktion“) rot zu zeigen.

### 6.3 Mutationsnachweis Escape-Pfad

Analog wurde in einer zweiten temporären Kopie ausschließlich der
Escape-`keydown`-Handler entfernt. Test 6 fällt dann ohne Ersatzweg:

```
test_overview_focus_enlarges_one_card_and_unlocks_scroll ... FAIL
...
  File ".../test_ap20_output_overview_ui.py", line 1217, in test_overview_focus_enlarges_one_card_and_unlocks_scroll
    self.wait_normal(target, timeout=8)
...
AssertionError: Karte ses_ap20_a wurde nicht auf Normalgröße zurückgestellt: class='bv-view bv-sub enlarged' box={'x': 8, 'y': 8, 'width': 1384, 'height': 884}

Ran 1 test in 12.786s
FAILED (failures=1)
```

Damit ist der Escape-Pfad eigenständig abgesichert; ein fehlender Handler
wird nicht mehr durch einen Ersatz-Klick maskiert.

## 7. Grüner Lauf gegen den aktuellen Arbeitsbaum

Nach den parallelen Fixes des coding-agent (Haupt-Fokus-Handler und
`sichtbarer Leerzustand`) wurde die vollständige Suite erneut ausgeführt:

```bash
cd /home/nutzer/vibe-logs/worktrees/vibe-AP20-yBZNBt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.browser.test_ap20_output_overview_ui -v
```

Rohausgabe (Auszug):

```
test_b11_f30_contract_remains_with_six_subagents ... ok
test_card_button_and_overview_focus_share_the_same_state ... ok
test_main_agent_header_focus_button_enlarges_main_view ... ok
test_overview_focus_enlarges_one_card_and_unlocks_scroll ... ok
test_second_focus_click_restores_normal_mode ... ok
test_session_switch_with_active_focus_keeps_no_orphan_state ... ok
test_zero_running_subagents_shows_empty_overview ... ok
test_subagent_cards_wrap_into_rows_within_the_panel ... ok
test_finished_subagent_leaves_overview_and_view ... ok
test_overview_lists_all_agents_with_compact_rows ... ok
test_narrow_viewport_has_no_horizontal_overflow_at_900 ... ok
test_normal_mode_has_no_nested_scrollbars_at_1400 ... ok

Ran 12 tests in 34.460s

OK
```

Damit sind alle 12 Fälle grün. Die Assertions wurden für diesen Lauf nicht
abgeschwächt; die Rotnachweise in Abschnitt 5 und 6 bleiben gültig.

## 8. Blocker

Keine. Playwright/Chromium und das isolierte VIBE-Root funktionieren; die
Suite läuft reproduzierbar.

## 9. Hinweise für den Coding-Agent

- Der Fokus-Knopf der Übersicht liegt im Fokus-Modus unter der
  ansichtsfüllenden Karte. Test 7 und 8 lösen den zweiten Klick auf den
  Übersichts-Knopf deshalb programmatisch aus (`node.click()`), um denselben
  Handler zu prüfen; alle anderen Aktionen laufen über echte Klicks/Tastatur.
- Der Haupt-Fokus-Knopf liegt im Kopf der fest positionierten Hauptansicht
  und bleibt im Fokus-Modus echt klickbar; Test 9 prüft dort Escape **und**
  den zweiten Klick.
- Escape ist in Test 6 der verbindliche Pfad; der zweite Klick hat einen
  eigenen Test (7). Ein pauschaler Ersatzweg existiert nicht mehr.
- Im Normalmodus darf Text in `.bv-log` abgeschnitten werden; die Tests
  verlangen nur `overflow-y: hidden` und dass die Live-Ausgabe im DOM
  ankommt (Fokus zeigt sie vollständig).
- „Höchstens ein Scrollbereich“ gilt im Normalmodus für den panelweiten
  Container, im Fokus-Modus für die Ausgabefläche der fokussierten Ansicht.
- Der Null-Subagenten-Test verlangt einen sichtbaren Leerzustandstext; der
  Zähler „0 Subagenten“ allein erfüllt die Anforderung nicht.

## 10. Abschlussprüfung durch den Koordinator (Rohausgabe)

Nach den Reviewfixes (Haupt-Fokus-Handler, Tooltip in den Übersichtszeilen,
Leerzustand ohne Subagenten) hat der Koordinator alle Prüfungen erneut im
Paket-Worktree ausgeführt. Zwei vorläufige `verify.sh`-Versuche mit einem leeren
temporären Projekt scheiterten an fehlender `.vibe/project.env` bzw. fehlendem
`VERIFY_QUICK`; nach Anlegen dieser nutzerlokalen Konfiguration verlief der
letzte Lauf erfolgreich. Rohausgabe der finalen Läufe:

```
$ python3 -m unittest tests.browser.test_ap20_output_overview_ui -v
test_b11_f30_contract_remains_with_six_subagents (...ContractTest...) ... ok
test_card_button_and_overview_focus_share_the_same_state (...FocusModeTest...) ... ok
test_main_agent_header_focus_button_enlarges_main_view (...FocusModeTest...) ... ok
test_overview_focus_enlarges_one_card_and_unlocks_scroll (...FocusModeTest...) ... ok
test_second_focus_click_restores_normal_mode (...FocusModeTest...) ... ok
test_session_switch_with_active_focus_keeps_no_orphan_state (...FocusModeTest...) ... ok
test_zero_running_subagents_shows_empty_overview (...FocusModeTest...) ... ok
test_subagent_cards_wrap_into_rows_within_the_panel (...GridTest...) ... ok
test_finished_subagent_leaves_overview_and_view (...OverviewTest...) ... ok
test_overview_lists_all_agents_with_compact_rows (...OverviewTest...) ... ok
test_narrow_viewport_has_no_horizontal_overflow_at_900 (...ScrollbarTest...) ... ok
test_normal_mode_has_no_nested_scrollbars_at_1400 (...ScrollbarTest...) ... ok
----------------------------------------------------------------------
Ran 12 tests in 26.142s

OK
EXIT=0
```

```
$ python3 -m unittest tests.browser.test_b11_output_ui tests.browser.test_f30_subagent_view_ui tests.browser.test_b14_subagent_output_ui tests.browser.test_ap16_syntax_highlighting_ui -v
... 20 einzelne "ok" (B11: 8, F30: 4, B14: 2, AP16: 6) ...
----------------------------------------------------------------------
Ran 20 tests in 55.128s

OK
EXIT=0
```

```
$ python3 scripts/check-import-manifest.py
OK: 57 Dateien stimmen mit docs/import-manifest.json überein.
EXIT=0

$ python3 scripts/check-syntax.py
OK: 187 Python-, 8 Bash- und 3 JSON-Datei(en) syntaktisch geprüft.
EXIT=0

$ python3 scripts/check-no-secrets.py
OK: keine Geheimnisse erkannt.
EXIT=0

$ node --check bin/web/app.js
EXIT=0   (keine Ausgabe)

$ bash scripts/verify.sh quick --project /tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap20-koordinator-projekt
=== vibe-Prüfung: quick ===
Projekt: /tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap20-koordinator-projekt
Prüfverzeichnis: /tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/vibe-verify-j7qlw4dh
OK: 187 Python-, 8 Bash- und 3 JSON-Datei(en) syntaktisch geprüft.
OK: keine Geheimnisse erkannt.
OK: 57 Dateien stimmen mit docs/import-manifest.json überein.
Prüfverzeichnis entfernt: /tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/vibe-verify-j7qlw4dh
OK: Prüfung 'quick' erfolgreich. (Exit 0)
EXIT=0

$ git diff --check
EXIT=0
```
