# AP7 Review — Runde 2

Reviewer: code-reviewer (unabhängig, read-only)
Datum: 2026-11-10
Grundlage: Ausgangsstand `28cf66d` → Arbeitsbaum, Ticket AP7 (TICKETS.md:693),
nach Behebung der Runde-1-Befunde (Ablage: `docs/reviews/AP7-review-1.md`).

Die Antwort des Reviewers wird inhaltlich unverändert wiedergegeben
(offensichtliche Kodistrate der Agentenrückgabe wurde lesbar normiert):

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 3
- Minor/Info: 1 (Info)
- Verdict: CHANGES REQUIRED

**Nachrechnungen (diese Runde tatsächlich ausgeführt):**
1. Shell war anfangs kurzzeitig erlaubt, wurde dann wieder verweigert: Die **erlaubten Rufe** waren ausschließlich Git-Lesebefehle (`git status --short`, `git diff --stat HEAD`, drei `git diff HEAD -- <pfad>` für styles.css, app.js, alle Testdateien, docs/import-manifest.json). **Wieder verweigert:** `grep` und `git diff | head` (Pipe), `node --check bin/web/app.js`, `python3 scripts/check-syntax.py` und weitere Python-Aufrufe — Syntax-, Manifest-Prüfsummen- und **alle Testläufe sind weiterhin Agent-Angaben** (inkl. „7/7 OK", „37/37 OK", verify.sh quick Exit 0, full-Discovery-Zahlen). Suchen habe ich über das grep-Tool, Dateilesen über read erledigt.
2. **Git-Diff vollständig gelesen** (app.js, styles.css, 5 Testdateien, Manifest) — der Runde-1-Vorwurf „Change set ohne Diff nicht beweisbar" ist damit für den zwischenzeitlichen Stand entlastet: Ich habe die tatsächlichen Änderungen gegenüber `28cf66d` selbst gelesen.
3. **Trilium-Notiz erneut per MCP gelesen** (nur lesend): utcDateModified **unverändert** `2026-11-10 01:06:49.015Z` — identisch zu meiner Runde-1-Lesung; siehe Befund M2.

## Sachlage der Runde-1-Befunde

| Runde-1-Befund | Status | Evidence |
|---|---|---|
| [Medium] Sprungziel unter fixer Kopfleiste | **Implementierung gelöst; Testsicherung unzureichend bindend** | `bin/web/styles.css` (AP7-Abschnitt): `.seccard,#project-agents{scroll-margin-top:56px}` — korrekte Gegenmaßnahme nach CSS-Semantik. Neuer Test `test_chip_jump_leaves_section_summary_below_fixed_header` (tests/browser/test_ap7_settings_ui.py:603–664) misst `.detailbar`-Bottom vs. `summary`-Top mit Toleranz −2 — **aber siehe Befund M1**: Die Messwerte im Report zeigen, dass das Ziel im Test-Regime **niemals an die Kopfleiste angeglichen** wird, also die Gefahrenstelle nie erreicht wird. |
| [Minor] Sandbox-Zustandsableitung doppelt | **gelöst** | `sandboxStatus(s)` in bin/web/app.js:179–185; genutzt von `settingsPanel` (app.js:186) und `sandboxBody` (app.js:588). Verhalten zur alten Doppelableitung identisch geprüft: `s` fehlend → `aus/mut`; `enabled` mit Fehler/`bwrap`/`missing` → gleiche Kette `Fehler → bubblewrap fehlt → Werkzeuge fehlen → bereit`; Töne identisch (`bad` auf `s.error‖!s.bwrap‖missing`). Kein Verhaltensdelta. |
| [Minor] Agenten-Chip „…"-Stillstand bei Ladefehler | **gelöst** | `projectAgentsCard(name,onPill)`: `load().catch` setzt `onPill('Fehler','bad')` (app.js-Diff, Funktion ab app.js:213); Zählerpfad setzt „n aktiv" ohne Tonwechsel (Pill bleibt `mut`). Einziger Aufrufer ist die neue Leiste (app.js:204; kein weiterer `projectAgentsCard`- oder toter `onCount`-Bezug — grep: 5 Treffer, alle konsistent). Test `test_agents_chip_shows_error_when_agents_api_fails` (test_ap7_settings_ui.py:666–700): deterministisch per `page.route(..., abort)`, prüft Fehlerbox, Pill-Text „Fehler" und `bad`-Klasse — sinnvoll gewählt, nicht zu starr (`wait_until` statt Momentaufnahme). |
| [Minor] Verweis auf `docs/reviews/AP7-review-1.md` | **gelöst** | Die Datei existiert und enthält meine Runde-1-Antwort unverändert (einschließlich Baseline-Vergleichsdetails), AP7.md:160 und :167–174 verweisen konsistent. |

**Neue Test-Agent-Helfer geprüft (git diff):** `mark_card()`/`wait_for_card_rebuild()` in test_sandbox_ui.py und test_write_dirs_ui.py setzen/lesen ausschließlich einen `dataset.staleMarker` — reines Warteverhalten gegen den asynchronen Detail-DOM-Ersatz. **Alle fachlichen Assertions blieben unverändert** (diff-zeilenweise nachgeprüft; einzige Entfernung: die Alt-Text-Sicherung „Sandbox (Shell und Build-Werkzeuge)" in test_sandbox_ui, ersetzt durch den dokumentierten Aufklapp-Schritt — siehe Info unten). Keine Abschwächung.

## Neue Befunde

- [Medium] `tests/browser/test_ap7_settings_ui.py:603–664` — Chip-Sprung-Test deckt den Runde-1-Befund-Regime nicht ab (Guard kann in der Fixtur nicht fallen)
  - Evidence: Die Messwerte des Reports (docs/reviews/AP7-test-agent-report.md:203–209) zeigen riesige Puffer (213/482/567 px) und einen veränderlichen `detailbar.bottom` (149→76): Für `#settings-rechte` war die Leiste noch unstuck, danach gerechnet — d. h. es wurde **kein Angleich-Scroll erreicht**. Ursache: Im Standardzustand passt der Inhalt in den 1000-px-Viewport (F13-Screenshot: Ende ≈ 630 px), die Zielsektionen liegen nah unten; `scrollIntoView({block:'start'})` kann das Ziel deshalb nicht an die Kopfleiste heranfahren. Genau dieses Angleich-Regime ist aber der Runde-1-Defekt-Fall — dort gilt: ohne `scroll-margin-top` läge `summary.top` bei ≤ 45 px unter der Leiste (76.06 px Höhe), mit 56 px bei ≈ 68 px, was sogar **unter** die Testvorgabe `bar.bottom − 2 = 74` fiele. Der Test kann in dieser Fixtur also auch dann nicht fallen, wenn das CSS entfernt wird; ob 56 px im echten Angleich-Regime ausreichen (zwingend wären ≥ ≈ 62 px nach eigener Invariante), ist mit den gelieferten Messwerten nicht belegbar.
  - Required fix: Testfall in das Angleich-Regime zwingen — z. B. konfigurierte Projektagenten in der Fixtur erzeugen (Muster `AGENT` aus tests/browser/test_write_dirs_ui.py) oder den Viewport stark verkleinern, sodass nach dem Chip-Klick Alignment möglich ist; zusätzlich `window.scrollY > 0` (Alignment wirklich erreicht) als Vorbedingung asserten und die Geometrie-Assertions beibehalten; falls die Invariante dann anmeckert, `scroll-margin-top` auf den gemessenen Bedarf (größer 56) anheben. Erst danach ist der Medium-Abhilfe-Nachweis aus Runde 1 tatsächlich erbracht.
- [Medium] Trilium-Notiz `vDzuhFgjY4PV` — seit den Runde-2-Fixes nicht synchronisiert
  - Evidence: MCP-Lesung: `utcDateModified: 2026-11-10 01:06:49.015Z` — identisch zu meiner Runde-1-Lesung; der Notiztext enthält weder `sandboxStatus` noch `scroll-margin-top`, nicht die 7-Fälle-Liste und nicht die neuen Testfälle/Prüfergebnisse. Die Repository-Doku (AP7.md) ist aktualisiert, die verbindliche Trilium-Doku hinkt hinterher (AGENTS: „Diese Dokumentation zusätzlich über den vorhandenen Trilium-MCP-Zugang dokumentieren"; DoD: Trilium tatsächlich durchgeführt) und steht teilweise in einem falschen Gegenwartsstand (u. a. 5-Fälle-Kontext).
  - Required fix: Trilium-Eintrag auf den Runde-2-Stand heben (7 Fälle inkl. der beiden neuen, Fixes aus Runde 1, aktuelle Prüfergebnisse), Schreiberfolg per Ablesung verifizieren.
- [Medium] Arbeitsbaum: 9 wiedergenerierte PNG-Nebenprodukte widersprechen der dokumentierten Grenzen-Aussage
  - Evidence: `git status` zeigt modifiziert (neben Soll-Nachweis F13-einstellungen.png): AP03-agenten.png, AP03-projekt-agenten.png, F13-uebersicht.png, F15-arbeitspakete.png, F16-rueckfragen.png, F27-trotz-aenderungen.png, F3-schreibrechte.png, F7-sandbox.png, V-011-modellkatalog.png. Der Test-Agent-Report (Zeile 261–263) bucht diese als mit `git checkout --` zurückgesetzt; die anschließende full-Discovery (84 Tests, vom Coding-Agenten zur Baseline-Zahlenerhebung) hat sie re-erzeugt. docs/features/AP7.md:189–192 behauptet daher aktuell falschen Baumbestand („weitere PNG-Aktualisierungen … wurden zurückgesetzt"). Bei Blanko-Staging würden „Screenshots ohne Nachweiswert" sowie Nachweise fremder Arbeitspakete mit dem AP7-Commit landen (AGENTS: Commit enthält ausschließlich dieses AP und seine Nachweise).
  - Required fix: vor dem Abschlusscommit die 9 Nebenprodukt-PNGs gegen HEAD zurücksetzen (`git checkout --`), nur F13-einstellungen.png behalten; AP7.md-Grenzen-Aussage mit dem finalen Baum abgleichen; vor dem Commit `git status` prüfen und ausschließlich AP7-Dateien stagen.
- [Info] `tests/browser/test_sandbox_ui.py` (Diff) — Alt-Titel-Assertion „Sandbox (Shell und Build-Werkzeuge)" ersatzlos entfernt
  - Evidence: unter dokumentierter Umbenennung („Sandbox (optional)") durch die gewollte Neugestaltung (Ticket erlaubt Umgestaltung). Der summary-Titel selbst wird in der Suite nicht mehr direkt gesichert (nur `#sandbox`-Knoten + Inhaltstexte); die F13-einstellungen.png-Auswertung zeigt den Titel. Kann so bleiben — falls Titelstabilität gesichert werden soll, eine Text-Assertion auf den summary-Titel ergänzen. Kein Mangel gegen das Ticket.

## Gelungene Kernprüfung der Fixes (Positiv-Nachweis)
- `sandboxStatus`-Refactor: Verhaltensidentität (oben tabelliert); die Schreib-API (`state`/`tone`) blieb identisch.
- `projectAgentsCard`-Signaturwechsel: alle Aufrufstellen angepasst, kein toter Code; Fehlerpfad setzt Pill bewusst mit Ton.
- Neue Bestands-Helfer: neutral, kein Assertionsverlust; die Delve um den asynchronen DOM-Ersatz ist fachlich plausibel (Server löst `detail()`-Refresh aus — bestätigt in app.js-Handlers `refresh()`).
- AP7.md: Interfaces, Tests-Liste (7 Fälle), Prüfergebnisse, Review-Abschnitt decken sich mit Code und Report; Verweis auf Runde 1 ist jetzt belegbar.

## Verification
- Change set geprüft: Ausgangsstand `28cf66d` → Arbeitsbaum, **diesmal über echte `git diff`-Einsichten** (app.js, styles.css, 5 Testdateien, docs/import-manifest.json) plus Set-Status (`git status --short`).
- Git-Befehle von mir ausgeführt: `git status --short`, `git diff --stat HEAD`, `git diff HEAD --` für styles.css, app.js, test_sandbox_ui.py+test_write_dirs_ui.py, test_ap06_github_ui.py+test_f20_harness_ui.py+test_project_detail_ui.py, docs/import-manifest.json.
- Checks mit mitgelieferten Objekten von mir direkt belegt: diff-basierte Änderungswahrheit aller Quell-/Test-/Manifest-Änderungen; Trilium-Stand (Stale-Befund belegt); Manifest-AP7-Eintrag liest Stand (app.js 108420 B, styles.css 9272 B, Resync von vibe_github.py/vibe_services.py dokumentiert).
- Checks **nicht** unabhängig ausgeführt (Shell für python/node/grep verweigert): `node --check`, `check-syntax.py`, `check-import-manifest.py` (Prüfsummen), unittest (7/7 und 37/37), verify.sh quick/full — weiterhin Agent-Angaben; Manifest-Prüfsummen unverifiziert.
- Wichtig geprüfte Bereiche: Runde-1-Fixstellen, Signals/Regime der neuen Tests, Test-Helfer-Integrität, Doku/Trilium/Image-Nachweise, Aufrufstellen.
- Remaining risks: die „7/7/37/37"- und Discovery-Vergleiche bleiben Agent-Angaben; die Chip-Sprung-Fix-Nachweisstärke im echten Align-Regime (M1) ist ungeprüft, weil kein Testlauf möglich; für den finalen Commit bleibt die Sauberkeitspflicht der PNG-Rücksetzung und die Trilium-Synchronisation offen (M2/M3).

**Verdict: CHANGES REQUIRED** — verbleibende Punkte:
1. [Medium] M1: Chip-Sprung-Test in das Align-Regime zwingen (Fixtur/Viewport), Alignment asserten; daraus `scroll-margin-top` ggf. auf ≥ ~62–76 px anheben.
2. [Medium] M2: Trilium-Notiz auf Runde-2-Stand aktualisieren (7 Fälle, Fixes, Prüfergebnisse) mit Ablesesicherung.
3. [Medium] M3: 9 PNG-Nebenprodukte gegen HEAD zurücksetzen, Doku-Grenzen-Aussage korrigieren, sauberer Staging-Schnitt beim Commit.
Danach Testläufe erneut melden und erneuter Review erforderlich — nur diese Punkte stehen zwischen Stand und PASS; die Implementierung selbst (app.js/styles.css) ist inhaltlich korrekt.
