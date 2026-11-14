# F30 — Test-Agent-Bericht (Rotphase)

Arbeitspaket: F30 „Sub Agent view" (Bug/Feedback-Eintrag, FEEDBACK.md)
Rolle: unabhängiger Test-Agent (`TESTER=test-agent`)
Ausgangsstand: Commit `5f6c8fe` (AP16), Branch
`vibe/vibe-F30-1794597769845746436-3112012-26243`; isolierte Kopie ohne `.git`
unter `/tmp/opencode/f30-redphase` (erzeugt mit `cp -a`, Verfahren wie bei
Paket B12 dokumentiert, `docs/reviews/B12-test-agent-report.md`).

## 1. Testherkunft

Die Testfälle wurden ausschließlich aus dem Arbeitspaket (FEEDBACK.md F30),
der Akzeptanzkriterienliste (AK1–AK7) und der belegten Ursachenanalyse des
Koordinators abgeleitet. Ein Implementierungsdiff existierte zum Zeitpunkt
des Schreibens nicht. Die Produktbasis wurde zur Schnittstellenklärung direkt
gelesen (`bin/vibe-web.py`: Handler `GET /api/subagent-output`,
`live_subagent_output`, `opencode_request`; `bin/web/app.js`: `outputView`,
`loadChild`, 2-s-Polling; `bin/web/styles.css`: `.bv-subs`, `.bv-sub`). Stil
und Fixture-Muster folgen den bestehenden B11-Suiten
(`tests/unit/test_b11_output_view_api.py`,
`tests/browser/test_b11_output_ui.py`) und dem B12-Muster
(`tests/unit/test_b12_background_subagents.py`) — ohne sie zu importieren,
verändern oder zu löschen.

Keine Modellaufrufe, keine externen Dienste: Der opencode-Server ist eine
lokale HTTP-Attrappe auf 127.0.0.1 (`ThreadingHTTPServer`), deren Verhalten
pro Test umschaltbar ist (live / nur Nutzernachricht / HTTP 500); das
Dashboard läuft in einem isolierten temporären VIBE-Root auf freiem Port;
tmux ist eine Attrappe; `env -u VIBE_RUNTIME`,
`PYTHONDONTWRITEBYTECODE=1`.

UI-Vertrag für AK6 (im Testdocstring fixiert): Vergrößern-Knopf ist ein
`<button>` in der laufenden Subagent-Karte mit nicht-leerem `aria-label`,
das „vergrö" enthält; vergrößert heißt ≥ 70 % Viewporthöhe und ≥ 60 %
Viewportbreite; zweiter Tastendruck stellt die Standardgröße wieder her.
Der Coding-Agent darf die Umsetzung frei wählen, muss aber diesen
zugänglichen Vertrag erfüllen.

## 2. Testdateien und Testbefehle

- `tests/unit/test_f30_subagent_view.py` (neu, 8 Tests, AK1–AK4)
- `tests/browser/test_f30_subagent_view_ui.py` (neu, 4 Tests, AK5–AK7)
- Testbefehl (Rotphase, gegen den unveränderten Ausgangsstand):

```
cd /tmp/opencode/f30-redphase && env -u VIBE_RUNTIME PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests.unit.test_f30_subagent_view -v
# Exit-Code: 1 — Ran 8 tests, FAILED (failures=3)
cd /tmp/opencode/f30-redphase && env -u VIBE_RUNTIME PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests.browser.test_f30_subagent_view_ui -v
# Exit-Code: 1 — Ran 4 tests, FAILED (failures=4)
```

Regressionssicherheit (AK4; Suite nicht verändert, bleibt grün):

```
cd /tmp/opencode/f30-redphase && env -u VIBE_RUNTIME PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests.unit.test_b11_output_view_api
# Exit-Code: 0 — Ran 11 tests, OK
```

## 3. Testfälle (Unit-Suite, `tests/unit/test_f30_subagent_view.py`)

| # | Test | AK | Rotphase |
|---|------|----|----------|
| 1 | `LiveOutputPreferredTest.test_live_output_wins_over_captured_state_output` | AK1 | **FAIL** |
| 2 | `LiveOutputPreferredTest.test_second_poll_returns_refreshed_live_output` | AK1, AK7 | **FAIL** |
| 3 | `CapturedOutputFallbackTest.test_captured_output_is_used_when_live_output_is_empty` | AK2 | ok (Regressionsschutz) |
| 4 | `CapturedOutputFallbackTest.test_captured_output_is_used_without_server_credentials` | AK2 | ok (Regressionsschutz) |
| 5 | `CapturedOutputFallbackTest.test_captured_output_is_used_when_the_server_fails` | AK2 | ok (Regressionsschutz) |
| 6 | `ClearMessageAndRegressionTest.test_no_output_anywhere_keeps_the_clear_message` | AK3 | ok (Regressionsschutz) |
| 7 | `ClearMessageAndRegressionTest.test_unknown_session_is_rejected_without_a_server_query` | AK4 | ok (Regressionsschutz) |
| 8 | `ClearMessageAndRegressionTest.test_live_fetch_is_attempted_even_when_output_is_captured` | AK4, AK1 | **FAIL** |

Details (Vorbedingung/Aktion/Erwartung/Fehlerfall) stehen in den Docstrings
der Testfälle.

## 4. Testfälle (Browser-Suite, `tests/browser/test_f30_subagent_view_ui.py`)

| # | Test | AK | Rotphase |
|---|------|----|----------|
| 1 | `CardSizeTest.test_subagent_cards_are_substantially_larger` | AK5 | **FAIL** |
| 2 | `EnlargeTest.test_running_card_can_be_enlarged_and_restored_by_keyboard` | AK6 | **FAIL** |
| 3 | `PollingRefreshTest.test_subagent_output_refreshes_on_polling` | AK7 | **FAIL** |
| 4 | `PollingRefreshTest.test_enlarged_card_keeps_showing_refreshed_output` | AK6, AK7 | **FAIL** |

Playwright/Chromium (headless, Viewport 1400×900) war verfügbar; die
Browser-Suite wurde tatsächlich ausgeführt (50,9 s Laufzeit).

## 5. Rotphasen-Ausgaben (wörtlich)

Unit-Suite (gekürzt auf die drei Fehler):

```
FAIL: test_live_output_wins_over_captured_state_output (tests.unit.test_f30_subagent_view.LiveOutputPreferredTest)
AK1: Live-Ausgabe wird geliefert, obwohl die Zustandsdatei voll ist.
AssertionError: 'LIVE-A-4711' not found in 'The subagent is working in the background (sessionID: ses_kind). STATISCH-4711' : Live-Ausgabe fehlt: 'The subagent is working in the background (sessionID: ses_kind). STATISCH-4711'

FAIL: test_second_poll_returns_refreshed_live_output (tests.unit.test_f30_subagent_view.LiveOutputPreferredTest)
AK1/AK7: Ein zweiter Abruf liefert den aktualisierten Text.
AssertionError: 'LIVE-A-4711' not found in 'The subagent is working in the background (sessionID: ses_kind). STATISCH-4711' : Erster Abruf liefert keine Live-Ausgabe: 'The subagent is working in the background (sessionID: ses_kind). STATISCH-4711'

FAIL: test_live_fetch_is_attempted_even_when_output_is_captured (tests.unit.test_f30_subagent_view.ClearMessageAndRegressionTest)
AK4/AK1: Auch mit erfasster Ausgabe wird chronologisch live gelesen.
AssertionError: [] is not true : Die Live-Ausgabe wurde nicht beim opencode-Server abgerufen (erfasste Ausgabe wurde bevorzugt): {"ok": true, "text": "The subagent is working in the background (sessionID: ses_kind). STATISCH-4711", "status": "running", "agent": "tester", "description": "tester arbeitet"}

Ran 8 tests in 4.007s
FAILED (failures=3)
```

Die Fehler belegen exakt die Ursachenanalyse: Der Endpunkt liefert den
statischen erfassten Text („The subagent is working in the background …")
und befragt den opencode-Server gar nicht.

Browser-Suite:

```
FAIL: test_subagent_cards_are_substantially_larger (tests.browser.test_f30_subagent_view_ui.CardSizeTest)
AK5: Subagent-Karten sind in der Standarddarstellung groß.
AssertionError: 150 not greater than or equal to 300 : Die Subagent-Karte ist mit 150 px zu klein (Ziel ≥ 300 px)

FAIL: test_running_card_can_be_enlarged_and_restored_by_keyboard (tests.browser.test_f30_subagent_view_ui.EnlargeTest)
AK6: Vergrößern per Tastatur, Rückkehr mit zweitem Enter.
AssertionError: unexpectedly None : Kein Vergrößern-Knopf (button mit aria-label „vergrö…“) in der Subagent-Karte gefunden; 0 Knöpfe vorhanden

FAIL: test_subagent_output_refreshes_on_polling (tests.browser.test_f30_subagent_view_ui.PollingRefreshTest)
AK7: Der Kartenkörper folgt dem Endpunkt beim 2-Sekunden-Polling.
AssertionError: Die Karte zeigt nicht die Live-Ausgabe (LIVE-A-4711)

FAIL: test_enlarged_card_keeps_showing_refreshed_output (tests.browser.test_f30_subagent_view_ui.PollingRefreshTest)
AK6/AK7: Auch die vergrößerte Karte aktualisiert sich weiter.
AssertionError: Die Karte zeigt nicht die Live-Ausgabe (LIVE-A-4711)

Ran 4 tests in 50.857s
FAILED (failures=4)
```

## 6. Erwartung an die Grünphase

Nach der Implementierung müssen alle 12 Fälle der beiden Suiten grün sein:

```
python3 -m unittest tests.unit.test_f30_subagent_view        # 8 Tests, OK
python3 -m unittest tests.browser.test_f30_subagent_view_ui  # 4 Tests, OK
python3 -m unittest tests.unit.test_b11_output_view_api      # 11 Tests, OK (Regression AK4)
```

Hinweise zur Umsetzung, die sich aus den Tests ergeben (fachliche
Schnittstelle, keine Lösungsvorgabe):

- AK1: `GET /api/subagent-output` muss die Live-Ausgabe
  (`live_subagent_output`, `order=asc`) bevorzugen und die erfasste
  Ausgabe nur als Fallback verwenden (leerer Live-Text, fehlendes
  Kennwort, Serverfehler).
- AK3: Die bestehende Meldung „Für diesen Subagenten liegt noch keine
  Ausgabe vor (Status: …)" mit `status`-Feld bleibt unverändert.
- AK5: `.bv-sub`-Höhe ≥ 300 px (Standarddarstellung) und `.bv-subs` ohne
  160-px-Höhenbegrenzung; gemessen wurde im Test die Bounding-Box der
  Karte `[data-agent-view][data-role='subagent']` und `clientHeight` von
  `.bv-subs`.
- AK6: Button-Vertrag s. o. Abschnitt 1 (aria-label mit „vergrö",
  Tastaturbedienung, ≥ 70 % Höhe / ≥ 60 % Breite, Rückkehr mit zweitem
  Enter).
- AK7: `app.js`-Karte folgt dem Endpunkttext beim 2-s-Polling — nach der
  Backend-Fixierung ist das End-zu-Ende erfüllt; eine eigene
  app.js-Änderung dafür ist nicht nötig (der Test prüft das Verhalten,
  nicht die Stelle).

## 7. Nicht getestet / Grenzen

- Die „doppelt"-Beobachtung des Feedbacks wird laut Koordinator nicht
  gefixt (zwei reale Kind-Sessions), nur dokumentiert — kein Testfall.
- Opencode-Fehlformen (401 trotz Kennwort, Verbindungsabbruch) sind nur
  über die Stellvertreterfälle HTTP 500 und fehlendes Kennwort abgedeckt;
  `opencode_request` behandelt alle Fehler gleich (`None` → leerer
  Live-Text), daher deckt das die Fallback-Semantik ab.
- AK5 „≥ 30 % der Ausgabeanzeige" ist als Zusatzbedingung zur 300-px-
  Grenze geprüft (Hauptansicht misst im Test ~40 % Viewport, d. h. die
  300-px-Grenze dominiert).
- Keine Modellaufrufe, keine externen Dienste, keine produktive
  Installation; alle Läufe in `/tmp/opencode/f30-redphase`.
