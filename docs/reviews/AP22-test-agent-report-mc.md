# AP22 — Testagent Meilenstein C: Agenten und erweiterte Parität

- **Arbeitspaket:** AP22 „New vibe UI“ (`docs/features/AP22.md`, Vertrag vom
  2026-11-20), Meilenstein C „Agenten + erweiterte Parität“.
- **Branch:** `feature/m0p/ap22`
- **Basis für die Rotphase:** Commit `4a5eeed` („AP22: Fundament der neuen
  UI — Shell, Startseite, Einstellungen …“). Während der Testarbeit ist durch
  einen anderen Agenten zusätzlich `a651321` (Design-Fix-Runde) entstanden;
  die Rotphase wurde bewusst auf dem beauftragten Stand `4a5eeed` erhoben.
  Dieser Bericht und die beiden Testdateien bleiben uncommittet.
- **Rolle:** unabhängiger Testagent — nur Tests und dieser Bericht; keine
  Implementierung, keine Commits, keine Änderung an `bin/`, `scripts/`,
  `docs/features/AP22.md`, `TICKETS.md` oder fremden Testdateien.

## Neu angelegte Testdateien

| Datei | Zeilen | Fälle | Prüft |
| --- | --- | --- | --- |
| `tests/browser/test_ap22_agents_ui.py` | 967 | 16 | Agentenliste, Wizard (4 Schritte, Rollen, Modell, Vorlage, Anlegen), Ein-Seiten-Editor (Felder, Rohmodus, Sicherung/Wiederherstellung, Kopieren, Löschen), Projektzuordnung |
| `tests/browser/test_ap22_advanced_ui.py` | 1203 | 10 | Models-Katalog, Profile-Vorschau/Anwenden, MCP (Maskierung, Schalter, Fehlertest), Kosten (Übersicht/Detail/Preise), Harness-Wechsel, Limits, Gates global+Projekt, Umgebung (Doctor/Pfade/Fritz/Emulator/Server), Runs-Prune, Feature-Paritätsrundgang |

Beide Suiten sind deterministisch und isoliert: temporäre Verzeichnisse, freie
Loopback-Ports, Attrappen für opencode/Pi/opencode-Server/Fritzbox, keine
Modellaufrufe, kein Netzwerk außerhalb von Loopback, Aufräumen in
`tearDownClass`. Chromium läuft headless aus dem Nur-Lese-Cache
(`PLAYWRIGHT_BROWSERS_PATH`, ersatzweise `~/.cache/ms-playwright`).

## Fachliche Abdeckung

### `test_ap22_agents_ui.py`

- **Liste:** `div[data-nv-agent-list]`, Karten `article[data-nv-agent="<name>"]`
  mit Rolle `[data-nv-role]`, Modell und Beschreibung, Vibe-Kennzeichnung,
  Neuanlage `[data-nv-action="agent-new"]`; eine defekte Agentendatei
  (`mode: quatsch`) ist als ungültig markiert (Textprüfung, da der Vertrag
  keinen eigenen Hook nennt).
- **Wizard:** `[data-nv-wizard]` mit `section[data-nv-step="1"]` … `"4"`;
  Name/Beschreibung/Rolle in Schritt 1 (Rollen aus dem fachlichen Katalog),
  Modell-Select in Schritt 2 aus der opencode-Attrappe, Prompt-Vorlage in
  Schritt 3 (`[data-nv-action="prompt-template"]` → `POST
  /api/agent_template`), Prüfen/Anlegen in Schritt 4
  (`[data-nv-action="agent-create"]`). Anlegen wird über die entstandene
  Datei **und** die neue Karte geprüft; ein leerer Name erzeugt
  `[data-nv-form-error]` ohne Datei.
- **Ein-Seiten-Editor:** alle strukturierten Felder auf einer Seite
  (Beschreibung, Modus, Modell, Temperatur, Schritte, Rechte, Prompt),
  Speichern überlebt Reload, Rohmodus zeigt Frontmatter, Digest-Konflikt wird
  als Formularfehler abgelehnt, Sicherung/Wiederherstellung, Kopie in der
  Liste, Löschen entfernt Datei und Karte.
- **Projektzuordnung:** `[data-nv-assign="proj"]` plus
  `select[data-nv-assign-model="proj"]`; Ergebnis über
  `GET /api/project-agents?name=proj` und nach Reload geprüft.

### `test_ap22_advanced_ui.py`

- **Models:** Katalog zunächst eingeklappt, Aufklappen sichtbar; Detailzeile
  trennt Fakten und Einschätzungen in getrennten Blöcken und nennt Quellen.
- **Profiles:** Liste der Profile; Vorschau zeigt Agent → Zielmodell, ohne
  `profiles.json` zu verändern; erst Anwenden setzt `aktiv` und das
  Agentenmodell.
- **MCP:** lokaler und entfernter Server; Token in der URL ist weder im DOM
  noch im Seitentext unmaskiert, `***` ist sichtbar; An/Aus-Schalter schreibt
  die Konfiguration; ein Test gegen eine geschlossene Loopback-URL liefert
  `[data-nv-mcp-result][data-nv-ok="false"]` mit Meldung.
- **Kosten:** Übersicht nennt Projekt und Tokens; Detail zeigt Paket/Modell;
  Preise (2 / 0.5 / 4) werden in `<install>/costs.json` gespeichert, die
  Kosten (3,1000 €) bleiben nach Reload erhalten.
- **Harness:** Status und Einrichtungsplan sichtbar; Wechsel auf Pi wird in
  `<state>/harness.json` gespeichert und überlebt Reload.
- **Limits:** Modus stop → continue → stop, jeweils in der UI und über
  `GET /api/limits` bestätigt.
- **Gates:** alle fünf Schlüssel mit Werten; globaler Wert, Projekt-Override
  und Entfernen des Overrides über `GET /api/gates[?name=proj]` bestätigt.
- **Umgebung:** Doctor-Zeilen mit bestandener und fehlgeschlagener Prüfung
  samt Hinweis; Pfade aus `/api/paths`; Fritz-Automatik an/aus, Reconnect über
  den nachgebildeten Helfer mit sichtbarer neuer IP; Emulator-Start ohne
  Android-Projekt meldet „Android“; opencode-Serverstatus sichtbar, Start/Stop
  vorhanden.
- **Runs:** Registereintrag aus `runs.json` (vor Serverstart geschrieben,
  Sitzung sicher fehlend); Prune markiert ihn als `ended`.
- **Parität:** alle 14 Feature-Schalter in `#/settings`; die fünf
  Projektfunktionen (github, writeaccess, sandbox, agentsfile, priority)
  erscheinen bei eingeschaltetem Feature im Projektbereich mit Überschrift
  und mindestens einem Bedienelement.

## Rotphase „Meilenstein C“

### Vorgehen

Die parallele Arbeit anderer Agenten verändert den Arbeitsbaum (A-Frontend
und Meilenstein-B-Tests). Damit die Rotphase nicht von diesen ungesicherten
Änderungen abhängt, wurde ein **sauberer Snapshot von `HEAD` (4a5eeed)**
erzeugt und nur die beiden neuen Testdateien hineinkopiert:

```
BASE=/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap22-mc-red
git archive HEAD | tar -x -C "$BASE"
cp tests/browser/test_ap22_agents_ui.py \
   tests/browser/test_ap22_advanced_ui.py "$BASE/tests/browser/"
cd "$BASE"
```

Ausgeführt wurden ausschließlich die beiden neuen Module. Der Arbeitsbaum
selbst wurde nicht verändert (keine Commits, keine fremden Dateien).

### `tests/browser/test_ap22_agents_ui.py`

Befehl:

```
PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright \
  python3 -m unittest tests.browser.test_ap22_agents_ui -v
```

Ergebnis:

```
Ran 16 tests in 401.570s

FAILED (failures=1, errors=15)
```

Repräsentativer Fehlschlag (fehlende Agentenliste):

```
FAIL: test_list_shows_agents_with_role_model_and_description
(tests.browser.test_ap22_agents_ui.ListTest.
 test_list_shows_agents_with_role_model_and_description)
AssertionError: 1 != 0 : Die Agentenliste div[data-nv-agent-list] fehlt
```

Repräsentativer Fehler (fehlender Editor):

```
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 25000ms exceeded.
Call log:
  - waiting for locator("[data-nv-agent-editor]") to be visible
```

Einordnung: `nova-agents.js` ist am Basisstand ein Platzhalter. Die
Agentenansicht rendert keine Liste, keinen Wizard und keinen Editor; damit
fehlen alle vertraglichen Hooks. Die Fehler sind **beabsichtigte Rotphase**
(fehlende Implementierung), keine Harness-Fehler: Server, Anmeldung,
Fixture-Dateien und Browser starten, die Liste-Assertion erreicht die Seite.

### `tests/browser/test_ap22_advanced_ui.py`

Befehl:

```
PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright \
  python3 -m unittest tests.browser.test_ap22_advanced_ui -v
```

Ergebnis:

```
Ran 10 tests in 195.621s

FAILED (failures=5, errors=7)
```

Die 5 Fehlschläge sind die fünf Projektbereiche des Paritätsrundgangs; die 7
Fehler sind die noch nicht gerenderten erweiterten Bereiche. Zwei Tests
bestehen bereits am Basisstand, weil Meilenstein A `limits` und `gates`
implementiert hat (`Ran 2 tests … OK` für
`GatesTest`/`LimitsTest`). Das belegt zugleich, dass Feature-Schalter,
Anmeldung und Harness funktionieren.

Repräsentativer Fehler (fehlender Bereich `models`):

```
ERROR: test_catalog_expands_and_separates_facts_from_assessments
(tests.browser.test_ap22_advanced_ui.ModelsTest.
 test_catalog_expands_and_separates_facts_from_assessments)
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 25000ms exceeded.
Call log:
  - waiting for locator("[data-nv-advanced='models']") to be visible
```

Repräsentativer Fehlschlag (fehlender Projektbereich `github`):

```
FAIL: test_every_feature_toggle_and_project_sections
(tests.browser.test_ap22_advanced_ui.ParityTest.
 test_every_feature_toggle_and_project_sections) (project_section='github')
AssertionError: 1 != 0 : Der Projektbereich 'github' fehlt bei
eingeschaltetem Feature
```

Alle sieben Bereichsfehler warten auf genau einen der noch fehlenden Hooks:
`[data-nv-advanced='models|profiles|mcp|costs|harness|env|runs']`. Die
Projektansicht ist am Basisstand ebenfalls ein Platzhalter; daher fehlen
`[data-nv-psection='…']` für alle fünf Projektfunktionen.

### Einordnung der Rotphase

- **Beabsichtigt rot:** Agentenliste, Wizard und Editor fehlen vollständig
  (`nova-agents.js` Platzhalter); die erweiterten Bereiche `models`,
  `profiles`, `mcp`, `costs`, `harness`, `env`, `runs` werden nicht gerendert
  (`nova-settings.js` rendert nur `limits` und `gates`); die Projektansicht
  ist ein Platzhalter.
- **Nicht rot, absichtlich:** `limits` und `gates` sind bereits umgesetzt und
  bestehen. Das ist kein Testfehler, sondern zeigt die Wirksamkeit der
  Feature-Schalter und der neuen Paritäts-Endpunkte.
- **Keine Harness-Fehler:** Der Server startet, die Token-Datei wird gelesen,
  Chromium startet, die Fixtures (Agenten, Modelle, MCP, Kosten-DB,
  `runs.json`, Fritz-Helfer) werden akzeptiert. Die Fehlschläge betreffen
  ausschließlich fehlende DOM-Hooks bzw. fehlende Projektbereiche.

## Vertragsableitungen und Ambiguitäten

Der Vertrag schreibt für die meisten erweiterten Unterelemente keine eigenen
Hooks fest. Die Tests dokumentieren die verwendeten Namen im Moduldocstring
von `test_ap22_advanced_ui.py`; die wichtigsten Ableitungen:

1. **Rollenkatalog:** `GET /api/agents` liefert `roles` als Zuordnung
   *Agent → Rolle*, keinen Katalog. Der fachliche Katalog ist
   `ROLE_NAMES` (`coder`, `reviewer`, `vibe`, `tester`, `analyst`,
   `sonstiges`, `content-creator`). Der Test verlangt die dokumentierten
   Rollen, nicht deren Reihenfolge.
2. **Editor-Felder:** Der Vertrag nennt die Felder, aber keine Hooks. Der Test
   bindet an `[data-nv-field="description|mode|model|temperature|steps|permissions|prompt"]`;
   die Temperatur wird als `input`, der Prompt als `textarea` geprüft.
3. **Ungültig-Markierung:** Kein Hook im Vertrag; der Test akzeptiert die
   Textmarker „ungültig/ungueltig/invalid/defekt“ innerhalb der Karte.
4. **Projektzuordnung:** Der Vertrag nennt nur `[data-nv-assign="<projekt>"]`;
   der Modell-Override wird als `select[data-nv-assign-model="<projekt>"]`
   geprüft.
5. **Profile:** Der Vertrag verlangt „Vorschau/Bestätigung“, beschreibt aber
   keinen Ablauf. Geprüft wird eine Vorschau vor dem Anwenden
   (`[data-nv-action="profile-preview"]` → `[data-nv-profile-preview]`) und
   anschließendes Anwenden (`[data-nv-action="profile-apply"]`).
6. **MCP-Fehlertest:** Für die strukturierte Fehleranzeige wird
   `[data-nv-mcp-result][data-nv-ok="false"]` mit sichtbarer Meldung
   verlangt. Die Attrappe nutzt eine geschlossene Loopback-URL (schneller,
   deterministischer Netzwerkfehler).
7. **Kosten:** Der Vertrag nennt nur „Übersicht, Detail, Preise“. Die
   abgeleiteten Hooks sind `[data-nv-cost-project]`, `[data-nv-cost-detail]`,
   `[data-nv-cost-model][data-nv-cost-field]` und
   `[data-nv-action="cost-save"]`. Die Kosten 3,1000 € folgen aus der
   Fixture-Rechnung (400k direkt + 600k cached zu 2/0,5 €, 500k Ausgabe zu 4 €
   je 1 Mio. Tokens).
8. **Harness-Einrichtungsplan:** Kein Hook im Vertrag; geprüft wird sichtbarer
   Text mit Installations-/Hinweisbegriffen (`install`, `einrichten`,
   `pi.dev`, `Hinweis`). Der Wechsel wird zusätzlich über
   `<state>/harness.json` verifiziert.
9. **Umgebung:** Doctor-Zeilen werden über `[data-nv-doctor-row]` mit
   `data-nv-ok` geprüft, Pfade über `[data-nv-paths]`, Fritz-Ergebnis über
   `[data-nv-fritz-result]`, Serverstatus über `[data-nv-server-status]`.
   Die Fritz-Automatik hat getrennte An/Aus-Knöpfe, weil der Auftrag
   „automation on/off buttons“ nennt.
10. **Priority:** Die Paritätsmatrix führt `priority` unter „Arbeit“, der
    Auftrag zu Meilenstein C nennt es als Projektbereich. Der Rundgang
    akzeptiert deshalb `[data-nv-psection="priority"]` **oder** den
    dokumentierten Arbeitsbereich `[data-nv-priority]`.
11. **Sprache:** Die neue Suite setzt vor jedem Fall Deutsch (`POST
    /api/language`), damit Backend-/Quelltexte (Doctor-Labels, Modusnamen)
    stabil prüfbar sind. Die Agenten-Suite prüft sprachunabhängig über Hooks
    und Dateien.
12. **Bereits implementierte Bereiche:** `limits` und `gates` werden tiefer
    geprüft als in der A-Suite (Moduswechsel, globaler Wert, Projekt-Override,
    Entfernen). Sie sind am Basisstand grün; das ist gewollt und kein
    Rotphase-Widerspruch.

## Nicht geprüft / bewusst nicht vertieft

- **Echte Prozesse:** Der opencode-Server wird nicht gestartet/gestoppt und
  der Emulator nicht ausgeführt. Geprüft werden Status, Knöpfe und die
  fachliche Fehlermeldung ohne Android-Projekt. Ein echter Start würde
  Prozesse und Ports außerhalb des Testrahmens erzeugen.
- **Echte Fritzbox:** Der Reconnect läuft ausschließlich gegen den
  nachgebildeten Helfer; es wird kein Router kontaktiert.
- **Echte MCP-Server:** Der Verbindungstest nutzt eine geschlossene
  Loopback-URL; es werden keine externen Server oder OAuth-Flows kontaktiert.
- **Echte Modelle:** Alle Modelllisten stammen aus Attrappen; es gibt keine
  Modellaufrufe.
- **Tiefe Projektfunktionen:** GitHub, Schreibrechte, Sandbox und AGENTS.md
  werden im Paritätsrundgang nur mit Überschrift und einem Bedienelement
  geprüft. Die tiefen Abläufe gehören zu den Meilenstein-B-Suiten und werden
  hier nicht dupliziert.
- **Screenshots:** Für Meilenstein C werden keine Screenshots erzeugt; die
  Prüfung erfolgt über DOM-Hooks und Dateizustand.

## Ergebnis

Die beiden Suiten bilden die Fachlichkeit von Meilenstein C ab und sind der
Maßstab für die Implementierung. Am Basisstand `4a5eeed` sind sie wie
dokumentiert rot (Agenten: 16 Fälle, 1 Fehlschlag/15 Fehler; erweiterte
Parität: 10 Fälle, 5 Fehlschläge/7 Fehler, davon `limits` und `gates` bereits
grün). Es wurden keine Produktionsdateien, fremden Tests, Dokumente oder
Commits verändert.

## Polier-Runde

Nachträgliche Runde auf derselben Testlinie: drei Lücken/Defekte in den
eigenen Tests wurden bearbeitet. Keine Produktionsdateien, keine fremden
Tests, kein Commit.

- **Rotphase Sessions-Limit (AP22-Paritätslücke):** Die beiden neuen Fälle
  `SessionsApiTest.test_sessions_limit_post_persists_and_is_reported` und
  `test_sessions_limit_invalid_values_change_nothing` sind am aktuellen Stand
  rot: `POST /api/sessions {"name":"proj","action":"limit","limit":7}`
  antwortet HTTP 400
  `{"ok": false, "message": "Unbekannte Aktion für /api/sessions: nur 'continue' wird unterstützt."}`.
  Erwartet ist CLI-Parität — `200 {"ok":true,"limit":7}`, persistiert über
  `vibe_runs.SessionRegistry(runtime).set_limit(7)` und sichtbar in
  `GET /api/sessions`; ungültige Werte (0, `"abc"`, > `SESSION_LIMIT_MAX`)
  und unbekannte Aktionen bleiben `ok:false` ohne Schreibvorgang. Alle
  übrigen 19 Fälle der Unit-Suite sind grün.
- **Profile-Anwenden (Wartebedingung geschärft, nicht geschwächt):** Der
  Profiles-Fall wartete bisher auf `profiles.json.aktiv == "kostenlos"` — in
  der Fixture bereits true, also ohne Aussage über die asynchrone Wirkung.
  Jetzt wird auf das echte Ziel gewartet: `tester.md` enthält nach dem
  Anwenden `opencode/vibe-modell` (Profil `kostenlos`, Rolle `coder`). Der
  Fall bleibt gegen die aktuelle synchrone Umsetzung grün und trägt eine
  spätere saubere asynchrone Implementierung.
- **Delegationsprüfung B2 (nur gelesen):** `bin/web/nova-project.js` ruft für
  `[data-nv-ppanel="output"]` `NV.output.render(name, panels.output)` auf;
  `bin/web/nova-output.js` registriert `NV.output.render(name, panelRoot,
  token)` (token optional). Kein Mismatch.

### Behobene Testdefekte (B1-Befund)

1. **Fehlender Helfer in `test_ap22_work_ui.py`:** `PriorityTest` rief
   `self.wait_api(...)` auf; der Helfer existierte nur in
   `test_ap22_project_ui.py`. Der Fall brach mit `AttributeError` ab, bevor
   er die Fachlichkeit prüfen konnte. Der Helfer ist jetzt in
   `AP22WorkBrowserTest` definiert (gleiches Polling, nutzt das lokale
   `api_json`); keine Imports aus dem anderen Testmodul.
2. **Falsche Antwortform-Annahme:** Der Priorisierungstest erwartete
   `order` als Liste von ID-Strings. Der eingefrorene Backend-Vertrag
   (`vibe_services.priority_info` → `vibe_packages.priority_view`) liefert
   Objekte `[{"id", "source", "title", "status"}]` — dieselbe Form, die die
   alte UI konsumiert. Der Test vergleicht nun die IDs
   (`[row["id"] for row in order]`); die Absicht bleibt unverändert
   (verschobenes Paket zuerst, Reihenfolge über den Reload stabil).
   Live-Server-Beleg (B1): `order[0].id == "AP-OPEN2"` nach dem Hochschieben
   und Speichern. `PriorityTest` ist grün.
