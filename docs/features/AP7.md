# AP7 — Einstellungs-UI neu aufgebaut

Stand: 2026-11-10
Ticket: TICKETS.md AP7 („Überarbeitung Einstellungen Ui im projekt“)
Arbeitsbranch: `vibe/vibe-AP7-1794266525738636934-788920-27568`
Basis-Commit: `28cf66d` (B8, Projektansicht ohne blockierende Git-Remote-Abfrage)

## Ausgangslage

Das Register „Einstellungen“ im Projekt-Detail war gewachsen: Agenten,
Schreibrechte, Sandbox und Git & GitHub lagen als vier Karten in einem
zweispaltigen `grid` untereinander — je nach Zustand weit über eine
Bildschirmseite, Wichtiges und Optionales waren nicht getrennt. Ohne Scrollen
war der Standardzustand nicht übersichtlich.

## Ziel

Neuentwicklung der Gliederung (Ticket: „von Grund auf neu“, wichtiges oben,
Optionales ggf. ausgeblendet, nur scrollen wenn unbedingt notwendig).
Reiner Frontend-Rebuild: `bin/web/app.js` und `bin/web/styles.css`;
Backend-APIs (`/api/project-agents`, `/api/rights`, `/api/sandbox`,
`/api/github`) bleiben unverändert.

## Neue Struktur

Das Register „Einstellungen“ (`#panel-einstellungen`, Registerknopf
`role=tab name="Einstellungen"` unverändert) zeigt von oben nach unten einen
einspaltigen Abschnittsstapel:

1. **Abschnittsleiste** `div.settings-nav[aria-label="Einstellungsbereiche"]` —
   vier Sprungknöpfe mit Statusanzeige:
   - `data-goto="agenten"` — „Agenten“ mit Zustandspill (Anzahl konfigurierter
     Agenten nach Ladeende, davor „…“).
   - `data-goto="rechte"` — „Schreibrechte“ mit „Standardliste“ bzw.
     „n Verzeichnisse“, bei Lese-/Schreibfehler „Fehler“.
   - `data-goto="sandbox"` — „Sandbox“ mit „aus|bereit|Fehler|
     bubblewrap fehlt|Werkzeuge fehlen“.
   - `data-goto="github"` — „Git & GitHub“ mit „aus|aktiv“.
   Jeder Knopf ist ein echter `<button class="b settingschip">`; Klick öffnet
   den zugehörigen Abschnitt und scrollt dorthin
   (`scrollIntoView({block:'start'})`); die Tastatur bedient die native
   Semantik (Enter/Space auf Button bzw. Summary).

2. **Agenten** — `section.card#project-agents`, dauerhaft geöffnet:
   Checkbox-Verwaltung der Projektagenten, Modell-Override, „Nicht
   konfigurierte Agenten anzeigen“ wie bisher (`data-toggle`, `data-configure`,
   `data-project-agent`, `data-model-override`).

3. **Schreibrechte (Agenten)** — `details.card#settings-rechte`, eingeklappt:
   Verzeichnisse für das Schreibwerkzeug der Projektagenten (`/api/rights`:
   „Hinzufügen“, „Entfernen“, „Standard wiederherstellen“, „Auf
   Projektagenten anwenden“). Karte behält den Erläuterungstext „Voreingestellt
   sind /tmp/opencode“.

4. **Sandbox (optional)** — „Sandbox (optional)” als `details.card#sandbox`,
   eingeklappt: einschalten/ausschalten, Prüfen, „Build-Werkzeuge“ speichern —
   alles wie bisher; Textkontrakte (u. a. „opencode-Server in bubblewrap“ bzw.
   die Pi-Variante) bleiben erhalten.

5. **Git & GitHub (optional)** — `details.card#github`, eingeklappt. Sichtbar
   immer: Aktiv-Checkbox, Repository, Label für vibe-Aufgaben, API-Basis,
   „Speichern“, „Mit GitHub verknüpfen“, „Verknüpfung lösen“.
   Der Aktionsteil — Branch-/Remote-Status, „Abrufen (fetch, kein Merge)“,
   „Push (Branch nach origin)“, „Pull (aufholen, --ff-only)“, „Merge-Request
   stellen“ und der Block „Issues als Arbeitspakete“ — erscheint erst mit
   aktiver Verknüpfung (`d.github.enabled`).

## Design-Entscheidungen

- **Status sichtbar statt Inhalt auf Vorrat**: Der Nutzer sieht am Chip
  sofort den Zustand eines Bereichs (Ton `ok|bad|mut`), ohne aufklappen oder
  scrollen zu müssen. KISS: keine neue Abstraktion und kein State-Store —
  reine Ableitung aus dem bereits empfangenen Detail-JSON (`d.sandbox`,
  `d.github`, `d.write_dirs*`).
- **`<details>`/`<summary>` statt Hidden-Div**: native Zugänglichkeit und
  Open/Close-Zustand ohne JavaScript-Store; die frühere Grid-Anordnung entfällt.
- **Standardzustand ohne Scrollen**: Leiste plus offener Agenten-Abschnitt
  passen in den ersten Bildschirmbereich; alles Optionale ist eingeklappt.
  Abgesichert im Test `test_settings_default_state_needs_no_hidden_content`.
- **Agenten-Pill nach Ladeende**: Die Agententabelle lädt asynchron
  (`/api/project-agents`); der Zähler im Chip wird erst nach dem Laden gesetzt
  (`onCount`-Rückruf). Der F13-Screenshot-Test wartet deshalb auf das
  Ladeende, bevor er den Standardzustand festhält.
- **Stabilitätskontrakte bewusst erhalten**: Tab-Name, Panel-ID, Karten-IDs
  (`#project-agents`, `#sandbox`, `#github`) und Button-/Labeltexte blieben
  unverändert, sodass die Bestandssuiten ohne fachliche Abschwächung
  weiterlaufen; nur ihre Helfer ergänzen den nötigen Aufklapp-Schritt.

## Interfaces (bin/web/app.js)

- `settingsPanel(d, name, isPi)` — baut Abschnittsleiste + vier Abschnitte;
  ersetzt den Grid-Aufruf in `detail()`.
- `settingsSection(id, title, open, body)` — `<details class="card seccard">`
  mit Summary und `.secbody`; gleiche visuelle Karten-Sprache.
- `projectAgentsCard(name, onPill)` — ergänzt um den Pill-Rückruf
  (`(text, tone)`) für den Agenten-Chip; setzt „n aktiv“ nach Ladeende und
  „Fehler“ bei Ladefehler.
- `sandboxStatus(s)` — einheitliche Ableitung des Sandbox-Zustands
  (`{state, tone}`), genutzt von Abschnittsleiste und Sandbox-Abschnitt.
- `rightsBody(d, name)`, `sandboxBody(d, name, isPi)`, `githubBody(d, name)` —
  die bisherigen Karteninhalte ohne eigenen Kartenrahmen und ohne eigenen
  Status-Kopf (übernimmt der Abschnitt bzw. die Leiste).
- CSS: `.settingsstack`, `.settings-nav`, `.settingschip`, `.seccard`
  (inklusive Summary-Marker und Open-Zustand), `.secbody`; optional
  `#project-agents` mit `scroll-margin-top:78px` gegen die fixe Kopfleiste
  (gemessene `.detailbar`-Höhe 76.06 px im Alignment-Regime);
  Bestandsregeln unverändert, neue Regeln im markierten AP7-Abschnitt.

## Manifest

`docs/import-manifest.json` wurde im selben Arbeitspaket nachgeführt:
`bin/web/app.js` und `bin/web/styles.css` wegen AP7; dazu `bin/vibe_github.py`
und `bin/vibe_services.py`, deren Prüfsummen bereits am Ausgangsstand `28cf66d`
unabhängig vom Manifest waren (B8 ohne Manifest-Sync, vorbestehender Defekt).
Der `aenderungen`-Liste wurde der AP7-Eintrag mit Grund und betroffenen
Dateien hinzugefügt.

## Tests (unabhängiger Test-Agent)

Neu: `tests/browser/test_ap7_settings_ui.py` (7 Fälle, Playwright/Chromium,
isolierter Dashboard-Server wie in den Bestandssuiten):
- `test_settings_tab_shows_section_nav_and_open_agents_first` — DOM-Reihenfolge
  (Leiste → Agenten → drei optionale Abschnitte), Agenten offen, Optionen
  eingeklappt, Chips mit Statuspill.
- `test_chips_open_optional_sections_without_full_reload` — Chip-Klick öffnet
  und scrollt; kein Neuladen.
- `test_chip_jump_leaves_section_summary_below_fixed_header` — Reviewrunde 1
  (Befund: fixe Kopfleiste überdeckt das Sprungziel): nach dem Chip-Sprung liegt
  der Zusammenfassungstitel unterhalb von `.detailbar` (Gegenmaßnahme
  `scroll-margin-top` für `.seccard, #project-agents`). In der Reviewrunde 2
  wurde der Test ins echte Alignment-Regime gezwungen (Viewport 1280×400,
  `scrollY > 0` als Vorbedingung); daraus folgte die Anhebung auf
  `scroll-margin-top:78px` (gemessene `.detailbar`-Höhe 76.06 px; Bindungs-
  nachweis: ohne Margin liegt `summary.top` bei 1.25/0.625/43.17 px, mit 56 px
  bei ≈57 px, beides unterhalb der Kopfleiste).
- `test_agents_chip_shows_error_when_agents_api_fails` — Agenten-Chip zeigt
  „Fehler“ (Ton bad) statt „…“, wenn `/api/project-agents` scheitert.
- `test_github_optional_blocks_hidden_when_disabled_collapse_and_after_enable`
  — GitHub-Aktionen und „Issues als Arbeitspakete“ nur bei aktiv.
- `test_settings_default_state_needs_no_hidden_content` — Standardzustand
  bedienbar, optionale Bedienelemente verdeckt.
- `test_keyboard` — Chips fokussierbar, Enter auf Summary klappt auf.

Angepasst (nur Helfer: Aufklapp-Zustand nach dem Abschnitt, neutraler
DOM-Ersatz-Marker gegen asynchrones Aufräumen — keine funktionalen
Abschwächungen): `test_sandbox_ui.py`, `test_write_dirs_ui.py`,
`test_ap06_github_ui.py`, `test_project_detail_ui.py`,
`test_f20_harness_ui.py`. Rot-/Grün-Protokoll:
`docs/reviews/AP7-test-agent-report.md`.

Screenshot: `docs/features/F13-einstellungen.png` zeigt den neuen
Standardzustand (Abschnittsleiste, offener Agenten-Abschnitt, eingeklappte
Optionen), erzeugt vom Test `test_project_detail_ui` nach Warten auf das
Ladeende (`input[data-toggle="unconfigured"]`) und mit harter Assertion
`assertNotIn("Lade Agenten", …)`.

## Prüfergebnisse

- `python3 -m unittest tests.browser.test_project_ui -v` → Ran 7 tests …
  OK (mehrere aufeinanderfolgende Läufe, reproduzierbar).
- `bash scripts/verify.sh quick` → Exit 0 (Manifest, Syntax, Geheimnisse).
- `bash scripts/verify.sh full` → Unit-Discovery: FAILED (failures=19,
  errors=61), Browser-Discovery: FAILED (errors=9, failures=0) — alles
  vorbestehend und am Ausgangsstand identisch reproduziert (Diff der
  Fehlermengen leer; die zwei Manifest-Bezugs-Failures am Ausgangsstand sind
  durch den AP7-Resync nun grün; Details siehe `docs/reviews/AP7-review-1.md`).
- Betroffene Browser-Suiten im Einzelrun grün: `test_sandbox_ui`
  (5/5), `test_write_dirs_ui` (5/5), `test_ap06_github_ui`,
  `test_project_agents_ui`, `test_ap03_agents_ui`, `test_project_detail_ui`
  (8/8), `test_f20_harness_ui`, `test_ap7_settings_ui` (7/7);
  Bestandssuiten-Runde vor der 78-px-Anhebung 37/37 OK (6 Suiten),
  nach der Anhebung 43/43 OK (7 Suiten).

## Review

Runde 1 (`docs/reviews/AP7-review-1.md`): CHANGES REQUIRED — behoben:
Sprungziel-Überdeckung durch die fixe Kopfleiste (`scroll-margin-top`,
anfangs 56 px), Sandbox-Zustandsableitung entdoppelt (`sandboxStatus()`),
Agenten-Chip-Fehlerzustand („Fehler“/bad) ergänzt, Doku-Verweis auf die
Review-Datei belegt.

Runde 2 (`docs/reviews/AP7-review-2.md`): CHANGES REQUIRED — behoben:
1) Chip-Sprung-Test ins echte Alignment-Regime gezwungen (Viewport 1280×400,
   `scrollY > 0` als Vorbedingung); daraus Anhebung auf
   `scroll-margin-top:78px` (gemessene `.detailbar`-Höhe 76.06 px).
2) Trilium-Notiz auf den aktuellen Stand synchronisiert (dieser Eintrag).
3) PNG-Nebenprodukte vor dem Abschlusscommit gegen HEAD zurückgesetzt; nur
   `docs/features/F13-einstellungen.png` bleibt als Nachweis geändert.
Der Reviewer bestätigte in Runde 2 die Runde-1-Fixes (sandboxStatus-
Verhaltensidentität, projectAgentsCard-Aufruf, Test-Helfer neutral).

## Trilium

Trilium-Eintrag: `vDzuhFgjY4PV` („AP7 Einstellungs-UI neu aufgebaut“,
Projektordner „vibe“ / „Features“, Labels #project=vibe, #arbeitspaket=AP7);
enthält Ziel, Struktur, Entscheidungen, Tests und Prüfergebnisse.

## Grenzen

- Discovery-„full“ in dieser Umgebung: `/_toolchain/agent-backups` ist
  read-only; die vorbestehenden Unit-Fehler beruhen hauptsächlich auf
  `BackupError: Sicherung nicht möglich … Read-only file system` sowie auf
  Startabhängigkeiten („vibe-web wurde vorzeitig beendet“, tmux/Konsole).
  Am Ausgangsstand dieselbe Fehlermenge.
- In diesem Paket wird neben Quell-/Test-/Manifest-Dateien nur
  `docs/features/F13-einstellungen.png` geändert (Nachweis des
  Standardzustands); weitere PNG-Aktualisierungen durch Testläufe wurden
  zurückgesetzt.
