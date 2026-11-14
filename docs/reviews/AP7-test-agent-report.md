# AP7 — Test-Agent-Bericht (Stand: vor der Umsetzung, Roter Lauf)

Kontext: Ticket AP7 „Überarbeitung Einstellungen Ui im Projekt“
(TICKETS.md, Zeilen 693–697). Die Tests wurden unabhängig aus Ticket, der
fachlichen Zielstruktur und AGENTS.md abgeleitet, nicht aus dem
Implementierungsdiff. Die Implementierung steht noch aus; die neue Suite ist
daher planmäßig rot.

## Testbefehle

Neue Suite (erwartet rot bis zur Umsetzung):

    python3 -m unittest tests.browser.test_ap7_settings_ui -v

Angepasste Bestandssuites (müssen gegen den augenblicklichen Code grün bzw.
neutral sein):

    python3 -m unittest tests.browser.test_sandbox_ui \
        tests.browser.test_write_dirs_ui tests.browser.test_ap06_github_ui \
        tests.browser.test_project_agents_ui tests.browser.test_ap03_agents_ui \
        tests.browser.test_project_detail_ui tests.browser.test_f20_harness_ui -v

Umgebung: jede Suite startet einen eigenen vibe-web-Prozess auf eigenem Port
mit vollständig isolierten VIBE_*-Pfaden; Chromium über Playwright headless
(`PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright`). Playwright und
Chromium sind installiert — kein BLOCKED.

## Neue Suite `tests/browser/test_ap7_settings_ui.py` (roter Lauf)

Klasse `Ap7SettingsBrowserTest`, 5 Fälle. Letzter Lauf: `Ran 5 tests in
60.740 s`, `FAILED (failures=2, errors=3)`.

### test_settings_tab_shows_section_nav_and_open_agents_first

* Vorbedingung: Projekt „proj“ geöffnet, Register „Einstellungen“ frisch
  aktiviert, nichts aufgeklappt.
* Aktion: Abschnittsleiste, Agentenabschnitt und die drei optionalen
  Abschnitte inspizieren.
* Erwartung: vier Chips (`data-goto` agenten/rechte/sandbox/github, je
  Bedienknopf) mit Status-Pills (Agenten „…“ oder Zahl, rechte
  „Standardliste“, sandbox „aus“, github „aus“); `#project-agents` offen und
  bedienbar; `#settings-rechte`, `#sandbox`, `#github` als eingeklappte
  `<details>` mit unsichtbarem Inhalt; DOM-Reihenfolge nav → Agenten →
  Schreibrechte → Sandbox → GitHub; Abschnittsleiste und Agentensteuerung
  ohne Scrollen sichtbar.
* Ergebnis: FAIL.
* Ursache: `div.settings-nav` existiert nicht — `chips_gotos()` liefert `[]`
  („Sprungknöpfe der Abschnittsleiste unvollständig“). Die optionalen
  Abschnitte sind im Bestandscode weiterhin offene `.card`-Divs, kein
  `<details>`-Zustand.

### test_chips_open_optional_sections_without_full_reload

* Vorbedingung: Register geöffnet, Marker `window.__ap7_marker` gesetzt.
* Aktion: Chips für Sandbox, Schreibrechte, Git & GitHub nacheinander klicken.
* Erwartet: jeder Zielabschnitt öffnet sich, ist im sichtbaren Bereich und
  zeigt seine Steuerelemente; ohne kompletten Seitenneuladen (Marker bleibt);
  der Agentenabschnitt bleibt offen.
* Ergebnis: ERROR.
* Ursache: Timeout (2000 ms) beim Klick auf
  `.settings-nav [data-goto="sandbox"]` — weder Leiste noch Chips sind
  implementiert.

### test_github_optional_blocks_hidden_when_disabled_collapse_and_after_enable

* Vorbedingung: Projekt ohne GitHub-Verknüpfung; GitHub-Abschnitt aufgeklappt.
* Aktion: Aktionsknöpfe und Issues-Block im aus-Zustand prüfen; Checkbox
  aktivieren, „Speichern“, Register einmal verlassen und neu öffnen.
* Erwartet: aus → „Abrufen (fetch, kein Merge)“, „Push (Branch nach origin)“,
  „Pull (aufholen, --ff-only)“, „Merge-Request stellen“ und der Block
  „Issues als Arbeitspakete“ unsichtbar; nach Aktivieren und erneutem Öffnen
  sichtbar; `GITHUB_ENABLED="1"` in project.env, `TYPE=generic` bleibt.
* Ergebnis: ERROR.
* Ursache: Timeout beim Warten auf `#github input[type="checkbox"]` — die
  Karte `#github` existiert im Bestandscode noch nicht (dort erhält die
  GitHub-Karte keinen eigenen Selector).

### test_settings_default_state_needs_no_hidden_content

* Vorbedingung: frisches Register, nichts aufgeklappt.
* Aktion: Agentenfilter bedienen; Sichtbarkeit der Eingaben der optionalen
  Abschnitte prüfen.
* Erwartet: Agentenfilter sichtbar, schaltbar; Build-Werkzeuge-, Verzeichnis-
  und Repository-Eingabe ohne Aufklappen unsichtbar.
* Ergebnis: FAIL.
* Ursache: „Build-Werkzeuge ist im Standardzustand sichtbar“ — der
  Bestandscode blendet alle Karten offen; es fehlen die eingeklappten
  `<details>`-Abschnitte.

### test_keyboard

* Vorbedingung: Register geöffnet.
* Aktion: erste Fokusposition im Panel prüfen, Chips durchtabben, Enter auf
  dem Sandbox-summary drücken.
* Erwartet: erster fokussierbarer Knoten des Panels ist der Agenten-Chip;
  Tab-Reihenfolge agenten → rechte → sandbox → github; Enter klaptt `#sandbox`
  auf und macht „Sandbox einschalten“ sichtbar.
* Ergebnis: ERROR.
* Ursache: Timeout (2000 ms) auf `.settings-nav [data-goto="agenten"]` — die
  Abschnittsleiste fehlt; die Fachstruktur (Chip zuerst) ist ungültig.

Zwischenfazit: alle fünf roten Fälle sind ausschließlich auf die fehlende
AP7-Strukturumsetzung zurückzuführen, nicht auf Umgebung, Testhelfer oder
Flüchtigkeiten.

## Anpassungen an Bestandstests (neutral, keine funktionalen Abschwächungen)

Grundsatz: Alle Bestandsdateien erhielten ausschließlich einen neutralen
Aufklapp-Helfer `expand_optional(...)`, der nur greift, wenn der Abschnitt als
`<details>` mit `> summary` umgesetzt ist. Auf dem augenblicklichen Code ist
der Aufruf ein No-op — die Bestandssuites bleiben jetzt grün und funktionieren
nach der AP7-Umsetzung genauso weiter. Keine Assertions gelöscht oder
abgeschwächt.

| Datei | Änderung | Ergebnis (augenblicklicher Code) |
|---|---|---|
| `tests/browser/test_sandbox_ui.py` | Aufklapp-Helfer; expandiert die Sandbox-Karte nach Registeröffnung und erneut nach jedem Kartenaufbau; vor der „Sandbox aktiv“-Kreuztext-Prüfung wird auch die Schreibrechte-Karte aufklappt (Text liegt künftig im Schreibrechte-Abschnitt); Screenshot nach dem Aufklappen. Zusätzlich erhielt die Suite die etablierte VIBE_*-Isolation (`ISOLATED_ENV` + explizite Laufzeitpfade), da sie in dieser Shell sonst vorbestehend gar nicht startbar ist — Assertions unverändert. | 1/1 ok (5,9 s) |
| `tests/browser/test_write_dirs_ui.py` | Aufklapp-Helfer; expandiert die Schreibrechte-Karte nach Registeröffnung und nach jedem Kartenaufbau (Hinzufügen, Entfernen, Zurücksetzen, Anwenden, Screenshot); der Bestätigungsdialog wird erst nach `wait_for(state="visible")` bestätigt, was den vorbestehenden detached-Flake an „Ja, zurücksetzen“ abfängt ( Assertions unverändert). | 4/4 ok (27,1 s; der zuvor beobachtete Baseline-Flake trat hier nicht auf) |
| `tests/browser/test_ap06_github_ui.py` | Aufklapp-Helfer in beiden Testklassen; `expand_optional("#github")` am Ende beider `open_project_settings`. | 9/9 ok (10,8 s) |
| `tests/browser/test_ap03_agents_ui.py` | keine Änderung nötig — laut Zielstruktur bleibt der Agentenabschnitt dauerhaft offen; die `#project-agents`- und Zeilen-Warter bleiben gültig. | 6/6 ok (2,7 s) |
| `tests/browser/test_project_agents_ui.py` | keine Änderung nötig (gleiche Begründung). | 3/3 ok (1,9 s) |
| `tests/browser/test_project_detail_ui.py` | Aufklapp-Helfer im „Werkzeuge speichern“-Ablauf (nach Registeröffnung und nach dem Neuladen); F13-Einstellungen-Screenshot entsteht weiterhin in `test_tabs_can_be_switched_by_mouse_and_keyboard` und zeigt künftig automatisch den neuen Standardzustand (Leiste oben, Agenten offen, Optionen eingeklappt). Außerdem dieselbe VIBE_*-Isolation wie bei test_sandbox_ui aus demselben vorbestehenden Startfehler. | 8/8 ok (7,8 s) |
| `tests/browser/test_f20_harness_ui.py` | Aufklapp-Helfer in der Basisklasse; `#sandbox` und `#settings-rechte` werden vor den Text-Betrachtungen aufgeklappt, weil die F20-/Regression-Hinweissätze künftig im eingeklappten `<details>`-Inhalt liegen. | 12/12 ok (3,9 s) |

Die Bestandstests bauen weiter auf den bestehenden Namen („Speichern“,
„Mit GitHub verknüpfen“, „Build-Werkzeuge“, `tr[data-project-agent]`,
`#sandbox`, `#github`/„Git & GitHub“, `.card` „Schreibrechte (Agenten)“),
damit sie nach der Umsetzung unverändert greifen.

## Umweltauflage (vorbestehend)

`test_sandbox_ui` und `test_project_detail_ui` brachten in dieser Shell ohne
explizite `VIBE_RUNTIME`-Isolation den Serverstart-Fehler
`OSError: [Errno 30] Read-only file system:
'/var/mnt/data/Dokumente/Informatik/VibeCode/_logs/.vibe-*.tmp'`
— der Server löst seinen Laufzeitordner ohne `VIBE_RUNTIME` auf den
produktiven `_logs`. Der Fix in den beiden Testdateien ergänzt nur die
im Repository bereits etablierte Isolation (Muster `test_write_dirs_ui`);
funktionsbezogene Assertions blieben identisch. Falls dieser Teil unerwünscht
ist, bleibt er wieder entfernbar — dann sind die beiden Suiten in dieser Shell
nicht startbar (vorbestehend, unabhängig von AP7).

## Nach der Umsetzung (Grüner Lauf + Robustheitsnachbesserungen)

Stand nach Umsetzung: `python3 -m unittest tests.browser.test_ap7_settings_ui
-v` → `Ran 5 tests in 63.012 s`, `OK` — dreimal in Folge grün (63,0 s,
63,0 s, 63,0 s): 5/5 bestanden.

Zwei Robustheitsfehler wurden ausschließlich in der Testdatei behoben
(Implementierung blieb unangetastet, keine Assertionsabstriche):

1. `test_chips_open_optional_sections_without_full_reload` — FAIL am Ende
   (`agents_toggle.is_visible()` False): Die Agententabelle lädt asynchron
   über `/api/project-agents`; der Sichtbarkeitsvergleich lief schneller als
   das Nachladen. Fix: nach `open_settings()` vor dem ersten Chip-Klick
   explizit `agents_toggle.wait_for()` (Sichtbarkeit) — die Erwartung selbst
   blieb unverändert sichtbar.
2. `test_github_optional_blocks_hidden_when_disabled_collapse_and_after_enable`
   — Der Test hinterließ `GITHUB_ENABLED="1"` in project.env; der alphabetisch
   vorn laufende Chip-Fall sah deshalb auf dem geteilten Server/Projekt den
   GitHub-Chip mit „aktiv“. Fix: Realistisches Freimachen am Testende über
   dieselbe UI-Naht — Register wechseln, `#github` aufklappen, Checkbox
   deaktivieren, „Speichern“, `wait_until`, bis `GITHUB_ENABLED="1"` in der
   Datei weg ist und `TYPE=generic` erhalten bleibt. Zusätzlich am Helfer
   `expand()`: ein zweiter summary-Click auf einen bereits geöffneten
   Abschnitt würde ihn zuklappen — der Klick passiert jetzt nur, wenn der
   Abschnitt geschlossen ist.

## Screenshot-Nacharbeit F13-einstellungen.png

Der Einstellungen-Screenshot (Standardzustands-Nachweis des AP7-Layouts in
`tests/browser/test_project_detail_ui.py`, Ablauf
`test_tabs_can_be_switched_by_mouse_and_keyboard`) zeigte zur Ablichtung
„Lade Agenten …", weil `/api/project-agents` beim ersten Screenshot-Zeitpunkt
noch lief. Fix ausschließlich in der Testdatei: vor dem Screenshot auf das
Ladeende-Signal der Agententabelle warten — `input[data-toggle=
"unconfigured"]` (erscheint erst nach Abschluss des Ladens, auch bei null
Agenten im Fixture) plus Assertion, dass die Ladezeile in
`#panel-einstellungen` nicht mehr enthalten ist. Keine Abschwächung.

Befehl: `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright
python3 -m unittest tests.browser.test_project_detail_ui -v`
Ergebnis: `Ran 8 tests in 28.106 s`, `OK` — 8/8 grün. Neu geschriebenes
`docs/features/F13-einstellungen.png` (Zeitstempel 01:51, 84 KB statt zuvor
58 KB): frischer Standardzustand mit Abschnittsleiste, offenem Agenten-
Abschnitt mit geladener Tabelle und drei eingeklappten Abschnitten, ohne
„Lade Agenten …". `docs/features/F13-uebersicht.png` war ein zufälliges
Nebenprodukt desselben Laufs und wurde mit `git checkout --` zurückgesetzt.

## Reviewrunde 1: Umsetzungstests (chip-jump, Fehlerzustand, Messwerte)

Neuer Fall `test_chip_jump_leaves_section_summary_below_fixed_header`
(Akzeptanz: Chip-Sprünge dürfen das Ziel nicht unter der fixen Kopfleiste
verstecken; Review-Runde-1-Medium-Befund):
Vorbedingung: Register „Einstellungen“ offen wie in den übrigen Fällen.
Aktion: nacheinander Chips rechte/sandbox/github klicken; nach jedem Sprung
die gerenderte Geometrie von `.detailbar` und `Ziel > summary` messen
(`getBoundingClientRect`).
Erwartet: `summary.top >= detailbar.bottom - 2`, `summary.height > 0`,
`summary.top >= 0` — Gegenmaßnahme `scroll-margin-top:56px` auf
`.seccard,#project-agents` (bin/web/styles.css, AP7-Abschnitt). Kein
smooth-scroll im CSS, die Messung direkt nach dem Klick ist final.
Ergebnis: GRÜN. Gemessene Werte (Instrumentation, danach entfernt):

* `#settings-rechte`: detailbar.bottom=149.0625, summary.top=362.25 →
  summary liegt 213 px unter der Unterkante der Kopfleiste.
* `#sandbox`: detailbar.bottom=76.0625, summary.top=557.625 → 482 px Puffer.
* `#github`: detailbar.bottom=76.0625, summary.top=643.171875 → 567 px
  Puffer.

Neuer Fall `test_agents_chip_shows_error_when_agents_api_fails`: blockiert
`/api/project-agents` deterministisch per `page.route(..., abort)`, prüft
die Kartenfehlermeldung „Agentenauswahl nicht verfügbar …“ und die
Agenten-Chip-Pill „Fehler“ mit Ton `bad` (Review-Runde-1-Minor-Fix des
Coding-Agenten). Ergebnis: GRÜN.

Ergebnisrunde: `python3 -m unittest tests.browser.test_ap7_settings_ui -v`
→ `Ran 7 tests in 63.5 s` / `OK` — zweimal hintereinander 7/7 grün.

## Bestandssuitenrunde: DOM-Ersatz-Race neutral behoben

Erster Bestandssuitenlauf (ohne korrektes `PLAYWRIGHT_BROWSERS_PATH`) fing
zwei Umgebungsartefakte als ERRORs ein (Chromium-Executable im Sandbox-Cache fehlt) — der
Lauf mit
`PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright` zeigte dieselben
zwei ERRORs als echte, reproduzierbare Testfehler:

1. `test_sandbox_ui.test_card_switches_on_sets_tools_checks_and_switches_off`
   — Klick auf „Prüfen“ TIMEOUT: `element is not stable`, schließlich
   `element was detached from the DOM`.
2. `test_write_dirs_ui.test_card_lists_defaults_and_persists_add_and_remove`
   — `wait_for` auf „Standardliste aktiv.“ löst 63× auf ein HIDDEN-Element.

Ursache (beide Male dieselbe Bauweise): Aktionen wie Sandbox ein/aus,
Werkzeuge speichern, Hinzufügen/Entfernen/Zurücksetzen lösen serverseitig
`detail(name)` aus, das das GANZE Detail-DOM asynchron ersetzt und
AP7-Optionalsabschnitte wieder einklappt. Die Tests warteten nur auf die
Datei-Wirkung (project.env bzw. permissions.json), die **vor** dem
DOM-Ersatz eintrifft, und arbeiteten damit teilweise noch auf dem alten,
später ersetzten DOM — der Klick lief in die Ersetzung hinein. Vor AP7 war
das unsichtbar, weil alle Karten immer sichtbar blieben; mit `<details>`
bricht die Naht auf.

Fix neutral, ausschließlich in den beiden Testdateien: ein Marker
(`el.dataset.staleMarker = '1'`) wird **vor** der auslösenden Aktion auf
den aktuellen Kartenknoten gesetzt; nach der Datei-Wirkung wartet der Test
deterministisch darauf, dass der Knoten ersetzt wurde (Marker weg), und
klappt erst dann ggf. wieder auf. Keine Assertionsabschwächung — die Fach-Erwartungen bleiben unverändert.
`mark_card()`/`wait_for_card_rebuild()` in beiden Dateien; angewendet an
je drei Aktions-Nähten (Sandbox ein/aus/Werkzeuge speichern;
Hinzufügen/Entfernen/Zurücksetzen).

Ergebnisse (jeweils `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright ...`):

* `python3 -m unittest tests.browser.test_sandbox_ui tests.browser.test_write_dirs_ui`
  → `Ran 5 tests in 33.5 s` / `OK` — 5/5 grün.
* Gesamte Bestandssuitenrunde:
  `python3 -m unittest tests.browser.test_sandbox_ui tests.browser.test_write_dirs_ui tests.browser.test_ap06_github_ui tests.browser.test_project_agents_ui tests.browser.test_project_detail_ui tests.browser.test_f20_harness_ui -v`
  → `Ran 37 tests in 78.1 s` / `OK` — 37/37 grün.
* AP7-Suite danach erneut: `Ran 7 tests in 63.5 s` / `OK` — 7/7.
* PNG-Nebenprodukte der Läufe (F13-uebersicht, F3-schreibrechte,
  F7-sandbox) mit `git checkout --` zurückgesetzt; nur
  `docs/features/F13-einstellungen.png` bleibt als Soll-Nachweis stehen.
  `docs/import-manifest.json`/`docs/trilium-index.md` ändern vom
  Coding-Agenten und wurden nicht angetastet.

## Reviewrunde 2: M1-Nacharbeitung (Alignment-Regime)

Befund M1 war berechtigt: In der Standardfixtur (1000 px Höhe) passt der
Inhalt in den Viewport; `scrollIntoView` kann das Ziel nicht an die
Kopfleiste heranfahren, die Invariante wäre auch ohne
`scroll-margin-top` bestanden.

Verschärfung in `test_chip_jump_leaves_section_summary_below_fixed_header`
(ausschließlich Testdatei):
- Viewport wird nach `open_settings()` auf 1280×400 verengt — der Inhalt
  übersteigt die Fensterhöhe, der Sprung erreicht das Alignment-Regime
  (Kontrast: bei 480 px war der `github`-Sprung am Scrollende gekappt und
  mit/ohne Margin identisch; bei 400 px bindend, `scrollY` 1035 vs 1049).
- Neue Vorbedingung je Chip: `window.scrollY > 0` nach dem Sprung.
- Invariante unverändert: `summary.top >= detailbar.bottom - 2`,
  `summary.height > 0`, `summary.top >= 0`.

Bindungsnachweis (Viewport 1280×400, probe-Läufe mit gespreiztem
`scroll-margin-top` via Style-Override, nicht committet): im
Alignment-Regime misst sich `summary.top ≈ scroll-margin-top`, ohne Margin
liegt das Ziel deutlich tiefer — die Assertion unterscheidet beide Regime:

| Chip | detailbar.bottom | sumTop@56px | sumTop@0px |
|---|---|---|---|
| `#settings-rechte` | 76.0625 | 57.25 | 1.25 |
| `#sandbox` | 76.0625 | 56.625 | 0.625 |
| `#github` | 76.0625 | 57.171875 | 43.171875 |

Ergebnis: **ROT mit dem gegenwärtigen 56px-Wert** — reproduzierbar in zwei
aufeinanderfolgenden Läufen (`Ran 7 tests`, je 1 failure):

`AssertionError: 57.25 not greater than or equal to 74.0625 :
Sprungziel #settings-rechte wird von der fixen Kopfleiste verdeckt
(summary.top=57.25 < detailbar.bottom=76.06; detailbar Höhe 76.06)`

Begründung/Messwert Lage: die fixe Kopfleiste `.detailbar` misst
`height=76.0625px`; im Alignment-Regime landet `summary.top` auf
`scroll-margin-top` (56) − Rundung. Für die Invariante
`summary.top >= 74.0625` muss `scroll-margin-top` folglich **≥ 76.0625
(+ Rundungsspielraum, z. B. 78–80px)** betragen oder die Köpfe-Höhe
reduziert werden. Exakte Soll-Referenz: `detailbar.bottom = 76.0625px`
(bei 400 px Viewport identisch). Keine Assertionsabschwächung — der
Coding-Agent hebt den Margin an.

Zusätzlich (R2-Info-Befund): in `tests/browser/test_sandbox_ui.py`
`test_card_switches_on_sets_tools_checks_and_switches_off` eine
Titel-Assertion auf den Aufklapp-Titel `Sandbox (optional)`
(`#sandbox > summary`) ergänzt.

Ergebnisse (`PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright ...`):
- `python3 -m unittest tests.browser.test_ap7_settings_ui -v` →
  `Ran 7 tests in 63.4 s`, `FAILED (failures=1)` — 6/7 OK; der einzige
  Fehlschlag ist der M1-Fall mit den exakten Werten oben (zweiter Lauf:
  `Ran 7 tests in 63.9 s`, identisches Bild).
- `python3 -m unittest tests.browser.test_sandbox_ui tests.browser.test_write_dirs_ui`
  → `Ran 5 tests in 33.5 s` / `OK` — 5/5 grün, zweimal.
- PNG-Nebenprodukte (F13-uebersicht, F3-schreibrechte, F7-sandbox, F8-*)
  nach den Läufen zurückgesetzt; nur `docs/features/F13-einstellungen.png`
  bleibt als Soll-Nachweis geändert.

## Stand (nach Reviewrunde 2 M1-Nacharbeitung)

* AP7-Suite: 6/7 grün (zweimal reproduziert); der M1-Fall
  `test_chip_jump_leaves_section_summary_below_fixed_header` ist solange
  ROT, bis `scroll-margin-top` auf ≥ ~78–80px angehoben wird
  (Soll-Referenz: `detailbar.bottom = 76.0625px`).
* Bestandssuiten: sandbox + write_dirs 5/5 grün (zweimal); Gesamtrunde
  37/37 grün unverändert aus der Folgebericht-Runde.
* Offen für den Coding-Agenten: CSS-Anhebung (`bin/web/styles.css`),
  danach erneute Ausführung der AP7-Suite.
