# AP16 — Testbericht des unabhängigen Test-Agenten

- Datum: 13.11.2026
- Arbeitspaket: AP16 „Syntax Highlighting in Ausgabe" (TICKETS.md, Zeile 997;
  „Die Agent ausgabe soll syntax highlighting erhalten, um besser lesbar zu
  sein.")
- Arbeitsbaum: `vibe-AP16-GPpTLE` (Branch
  `vibe/vibe-AP16-1794591454226957353-2736030-2574`, Basiscommit `cb1875d`)
- Tester: konfigurierter `TESTER=test-agent` (`.vibe/project.env`)
- Grundlage: AP16-Ticket, `FEEDBACK.md` (F19-Eintrag, Zeile 187 ff.),
  `docs/features/F19.md` (Highlighter- und DOM-only-Vertrag),
  `docs/features/B11.md` (Ausgabeansicht `[data-panel='ausgabe']`, `.bv-log`,
  Hauptagent + laufende Subagenten). Die Implementierungsdiffs
  (`bin/web/app.js`, `bin/web/styles.css`) wurden nicht als Testquelle
  verwendet.

## Herkunftserklärung

Die beiden AP16-Testdateien stammen aus einem abgebrochenen früheren Anlauf
dieses Pakets und lagen unversioniert vor (ohne Bericht). Ich habe sie als
konfigurierter Test-Agent vollständig gelesen und inhaltlich gegen das
AP16-Ticket und die abhängigen Paketdokumente (F19, B11) geprüft. Ich habe
sie hiermit übernommen und abgenommen:

| Datei | Fälle | Prüfung/Änderung | Grund |
|---|---|---|---|
| `tests/unit/test_ap16_syntax_highlighting.py` | 2 | unverändert übernommen | deckt AK4 (DOM-only-Quellvertrag, F19-Entscheidung) und AK6 (F19-Klassenvertrag `pre#log .hl-*`) als unabhängig prüfbare Quellverträge ab |
| `tests/browser/test_ap16_syntax_highlighting_ui.py` | 6 | unverändert übernommen | deckt AK1–AK6 in der echten Ausgabeansicht ab; prüft implementierungsunabhängig über berechnete Textfarben, nicht über Klassennamen |

Neu geschriebene Tests waren nicht nötig: Alle Akzeptanzkriterien sind durch
die bestehenden 8 Fälle abgedeckt (Zuordnung unten); es gibt keine Lücke.
Keine Assertion wurde abgeschwächt und kein Test entfernt.

## Zuordnung Testfälle → Akzeptanzkriterien

### AK1 — Hauptagentenansicht hebt Protokollzeilen hervor
- `tests.browser.test_ap16_syntax_highlighting_ui.MainAgentHighlightTest.
  test_main_agent_log_lines_are_visually_distinguished`
  - Vorbedingung: aktiver Lauf (Laufregister `running`); Hauptlog mit
    Protokollkopf-, Fehler-, Pfad-, schlichter und Markup-Zeile; Zustandsdatei
    mit Hauptsession und leerer Subagentenliste.
  - Aktion: Ausgabeansicht öffnen; berechnete Textfarben aller Textknoten der
    Hauptausgabe (`.bv-log`) messen.
  - Erwartung: Kopf-, Fehler- und Pfadtoken tragen eine andere berechnete
    Farbe als die schlichte Zeile; die schlichte Zeile trägt genau eine
    Farbe; Seite fehlerfrei (keine JS-Fehler, keine Browserdialoge).
  - Fehlerfall: Keine Farbdifferenz — keine Hervorhebung.

### AK2 — laufende Subagenten erhalten dieselbe Hervorhebung
- `MainAgentHighlightTest.test_subagent_log_is_highlighted_like_the_main_log`
  - Vorbedingung: aktiver Lauf; Subagent A (`ses_ap16_sub_a`, status
    `running`) mit Fehler- und schlichter Zeile in seiner erfassten Ausgabe.
  - Aktion: berechnete Farben in der Subagentenansicht
    (`[data-role='subagent'][data-session='ses_ap16_sub_a'] .bv-log`) messen.
  - Erwartung: Die Fehlerzeile unterscheidet sich farblich von der schlichten
    Zeile in derselben Ansicht; Text erhalten.
  - Fehlerfall: Subagentenausgabe bleibt ohne Hervorhebung.

### AK3 — der dargestellte Text bleibt exakt der Protokolltext
- Innerhalb von `test_main_agent_log_lines_are_visually_distinguished` (und
  in den übrigen Ansichtsfällen): `assert_text_preserved` prüft je Zeile
  (Kopf, Fehler, Pfad, schlicht, Markup), dass sie im `textContent` der
  Ausgabe exakt einmal enthalten und sichtbar dargestellt ist.
  - Fehlerfall: veränderter, fehlender oder doppelter Protokolltext.

### AK4 — Markup bleibt sichtbarer Text, nie HTML
- `MainAgentHighlightTest.test_log_markup_is_never_interpreted_as_html`
  - Vorbedingung: aktiver Lauf; Haupt- und Subagentenprotokoll enthalten
    `<script>`- (setzt `window.__ap16pwn`) und `<b>`-Markup.
  - Aktion: Ausgabeansicht öffnen; `window.__ap16pwn` prüfen; je Ansicht
    `<script>`-/`<b>`-Elemente zählen; wörtliche Anzeige prüfen.
  - Erwartung: Kein Skript ausgeführt, keine Markup-Elemente in den Ansichten,
    `<script>` wörtlich sichtbar; Seite fehlerfrei.
  - Fehlerfall: Markup wird als HTML interpretiert oder erzeugt Fehler.
- Quellvertrag `tests.unit.test_ap16_syntax_highlighting.
  AP16WebUiHighlightingTest.test_web_ui_never_interprets_log_content_as_html`:
  `bin/web/index.html`, `bin/web/styles.css` und `bin/web/app.js` enthalten
  keinen HTML-Injektionsaufruf (`.innerHTML`, `innerHTML =`, `insertAdjacent-
  HTML`, `outerHTML`, `document.write`); der erläuternde F19-Kommentar zählt
  nicht als Treffer.

### AK5 — Live-Zeilen erscheinen hervorgehoben und fehlerfrei
- `LiveHighlightTest.test_live_appended_error_line_is_highlighted`
  - Vorbedingung: aktiver Lauf, Ausgabeansicht geöffnet, Hauptlog mit
    schlichter und Fehlerzeile.
  - Aktion: Fehlerzeile an das Laufprotokoll anhängen (echter SSE-Live-Pfad).
  - Erwartung: Neue Zeile erscheint farblich von der schlichten Zeile
    unterschieden, genau einmal; keine JS-Fehler, keine Dialoge.
  - Fehlerfall: Neue Zeile ohne Hervorhebung, doppelt oder mit Fehlern im
    Live-Pfad.

### AK6 — F19-Lauf-Log sowie Steuern/Fortsetzen unberührt
- `LegacyRunLogTest.test_f19_run_log_keeps_its_highlighting`
  - Vorbedingung: beendeter Lauf ohne Sitzungsangabe (Rückfallmodus der
    „Live-Ausgabe“-Karte mit `pre#log`).
  - Aktion: Farben in `pre#log` messen; Vorhandensein von genau einem
    `pre#log` prüfen.
  - Erwartung: Kopf- und Fehlerzeilen unterscheiden sich farblich von der
    schlichten Zeile.
  - Fehlerfall: Die bestehende F19-Hervorhebung ging verloren.
- `LegacyRunLogTest.test_send_and_continue_controls_still_work`
  - Vorbedingung: aktiver Lauf; `/api/steer` abgefangen (route-Intercept).
  - Aktion: Anweisung eingeben und über den Senden-Knopf absetzen.
  - Erwartung: Textarea und Knopf freigegeben; kein Fortsetzen-Knopf während
    des Laufs; der abgefangene POST `/api/steer` enthält Projektname `proj`,
    die Hauptsession und den Anweisungstext.
  - Fehlerfall: Steuerung wurde durch die Hervorhebung beschädigt.
- Quellvertrag `AP16WebUiHighlightingTest.
  test_f19_highlight_classes_remain_scoped_to_the_run_log`: `styles.css`
  definiert die Regeln `pre#log .hl-head`, `pre#log .hl-err`,
  `pre#log .hl-tool`, `pre#log .hl-sub` — der dokumentierte F19-Vertrag
  (`docs/features/F19.md`, Abschnitt „Oberfläche“) bleibt bestehen.

## Ausführungsergebnisse (tatsächlich, Arbeitsbaum `vibe-AP16-GPpTLE`)

Gegen den unveränderten (uncommiteten) Arbeitsstand — Implementierung liegt
als Änderung an `bin/web/app.js` und `bin/web/styles.css` vor:

| Befehl | Ergebnis | Exit-Code |
|---|---|---|
| `python3 -m unittest tests.unit.test_ap16_syntax_highlighting -v` | **2 Tests, OK** (~0 s) | 0 |
| `python3 -m unittest tests.browser.test_ap16_syntax_highlighting_ui -v` | **6 Tests, OK** (~14 s) | 0 |
| `python3 -m unittest tests.browser.test_b11_output_ui -v` (Regression Ausgabeansicht B11) | **8 Tests, OK** (~25 s) | 0 |

Die Tests sind nicht attrappenhaft: Sie starten einen echten
`vibe-web`-Server (isoliertes VIBE-Root, eigene Ports, kein produktives
HOME/VIBE), befüllen Laufregister und Zustandsdatei über das echte
`vibe_runs.py` und prüfen echte berechnete Stile im Browser (Playwright/
Chromium). Keine echten Modellaufrufe, keine produktive Installation, keine
Netzzugriffe; steuernde POSTs werden abgefangen.

## Rotphasen-/Failing-first-Nachweis (Basisstand `cb1875d`)

Die Rotphase wurde zunächst durch den Koordinator am Basisstand `cb1875d`
nachgewiesen (3 Browsertests-Fehlschläge). Ich habe den Nachweis unabhängig
reproduziert:

### Vorgehen

1. Temporären, losgelösten Worktree am Basiscommit erzeugt:
   `git worktree add --detach <TMPDIR>/ap16-basis cb1875d` (Exit 0).
2. Die beiden AP16-Testdateien unverändert in denselben Pfad im
   Basis-Worktree kopiert; Byte-Identität je Datei mit `diff -q` geprüft
   (beide identisch).
3. Am Basisstand verifiziert: `bin/web/app.js` setzte die Ausgabeansicht per
   `textContent` ohne Hervorhebung — die AP16-Mechanik fehlt am Basisstand.
4. Browser- und Unit-Tests im Basis-Worktree ausgeführt.
5. Aufgeräumt: `git worktree remove --force` (Exit 0), temporäres Verzeichnis
   entfernt; `git worktree list` enthält keinen ap16-rotphase-Eintrag mehr;
   der Arbeitsbaum blieb unverändert (Implementierung uncommitet,
   Testdateien unversioniert, HEAD `cb1875d`).

### Ergebnisse je Modul (Basisstand `cb1875d`)

| Modul | Tests | Fehlschläge (erwartet) | am Basisstand grün |
|---|---|---|---|
| tests.browser.test_ap16_syntax_highlighting_ui | 6 | 3 FAIL | 3 |
| tests.unit.test_ap16_syntax_highlighting | 2 | 0 | 2 |
| **Summe** | **8** | **3** | **5** |

Fehlgeschlagene Testmethoden am Basisstand (exakt):

- `test_main_agent_log_lines_are_visually_distinguished` (AK1) —
  `FEHLERZEILE_ROT`/`PROTOKOLLKOPF_APX`/`bin/web app.js` trugen dieselbe
  berechnete Farbe wie die schlichte Zeile: keine Hervorhebung.
- `test_subagent_log_is_highlighted_like_the_main_log` (AK2) —
  `SUBFEHLER_ROT` farblich nicht von der schlichten Zeile unterschieden.
- `test_live_appended_error_line_is_highlighted` (AK5) — die live
  angehängte Fehlerzeile (`LIVEFEHLER_ROT`) erhielt keine eigene Farbe.
- Gesamt: `Ran 6 tests … FAILED (failures=3)`, Exit-Code 1.

Am Basisstand bereits grüne Fälle (5) — Einordnung:

- Die drei Browser-Gardisten (`test_log_markup_is_never_interpreted_as_html`,
  `test_f19_run_log_keeps_its_highlighting`,
  `test_send_and_continue_controls_still_work`) prüfen bestehendes
  F19-/B11-Verhalten, das AP16 bewusst nicht verändert; sie schlagen erst
  ein, wenn die Umsetzung den DOM-only-Vertrag verletzt, die F19-Karte ihre
  Hervorhebung verliert oder die Steuerung beschädigt. Sie sind bewusst
  Regressionsgardisten und am Basisstand grün.
- Die beiden Unit-Gardisten sind Quellverträge (DOM-only, F19-Klassen am
  `pre#log`), die am Basisstand bereits erfüllt sind; sie bewachen, dass die
  AP16-Umsetzung diese Verträge nicht verletzt.

Damit ist der Failing-first-Nachweis für AP16 erbracht: Genau die drei
Hervorhebungsfälle (AK1, AK2, AK5) fallen am Basisstand aus und sind nach
der Änderung grün. Alle Befehle wurden tatsächlich ausgeführt; kein Ergebnis
wurde interpoliert.

## Umgebungsaspekte

- Die Browsertests benötigen einen vorhandenen Playwright-Browser-Cache. Die
  Testdatei setzt `PLAYWRIGHT_BROWSERS_PATH` selbst auf
  `~/.cache/ms-playwright`, falls die Variable leer ist; in dieser Umgebung
  war der Cache vorhanden, alle Browserläufe liefen dadurch ohne
  Zusatzkonfiguration.

## Grenzen

- Die Hervorhebung wird über berechnete Textfarben geprüft, nicht über
  konkrete Klassennamen (bewusst implementierungsunabhängig); die
  Klassennamen-Bindung ist nur für die F19-Lauf-Log-Karte als dokumentierter
  Vertrag (Unit-Gardist) festgeschrieben.
- Die Browser-Tests decken den Desktop-Viewport 1400×900 ab; keine
  Responsive-/Touch-Prüfung.
- Mehrere gleichzeitig laufende Subagenten werden im AP16-Fall nur mit einem
  Subagenten geprüft; das gleichzeitige Verhalten mehrerer Flächen ist durch
  die B11-Regressionssuite (`test_b11_output_ui`, zwei laufende Subagenten)
  abgedeckt.
- Die Prüfungen wurden gegen den unveränderten Arbeitsstand ausgeführt; ein
  Commit oder Branchwechsel war für diese Prüfung nicht vorgesehen und
  erfolgte nicht.
