# Review AP22 — Gesamtabnahme (Runde 1)

- **Arbeitspaket:** AP22 „New vibe ui“ (`TICKETS.md`): Neuaufbau der gesamten
  Weboberfläche für nicht-/semi-technische Nutzer; alte UI bleibt als Option
  (standardmäßig aus); CLI-Parität als Qualitätskriterium.
- **Paketbranch:** `feature/m0p/ap22`; Commits unter Review:
  `4a5eeed` (Fundament), `a651321` (Design-Fix-Runde), `c3364fe`
  (Meilenstein B+C+Polier); Basis `f49940d`.
- **Rolle:** unabhängiger Review-Agent (code-reviewer). Offenlegung der
  Umstände: Vier vorherige Review-Anläufe scheiterten an
  Provider-Nutzungslimits bzw. am Schrittlimit, bevor eine Review-Datei
  entstehen konnte; dieser Lauf prüfte den Gesamtdiff `f49940d..c3364fe`
  und lieferte das Ergebnis als Abschlussbericht. Der Koordinator hat diese
  Datei mit dem wörtlichen Inhalt des Reviewer-Berichts angelegt; jede
  Bewertung und jedes Urteil stammt vom Review-Agenten.
- **Datum:** 2026-11-20
- **Prüfmethode:** Code-Lesen des Gesamtdiffs, Vertragsabgleich gegen
  `docs/features/AP22.md` und `SPEC.md`, Testberichts-Abgleich
  (`docs/reviews/AP22-test-agent-report.md`, `AP22-test-agent-report-mc.md`),
  klassischer UI-Vergleich (`bin/web/app.js`). Grünlauf-Aussagen des
  Koordinators wurden als FremdNachweis übernommen, nicht selbst erneut
  ausgeführt; die genannten Lücken sind durch Code-Lesen und die
  Selbstauskunft der Testberichte belegt.

## Summary

- Critical: 0
- High: 0
- Medium: 5
- Minor: 2
- **Verdict: CHANGES REQUIRED**

## Akzeptanzkriterien

| Kriterium | Status | Beleg |
| --- | --- | --- |
| `/` neue Shell, `/classic` alte UI unverändert | PASS | Routing in `bin/vibe-web.py`; `git diff f49940d..c3364fe -- bin/web/app.js bin/web/styles.css` leer; `classic.html` inhaltlich identisch zur alten `index.html`; `tests/unit/test_web_modularization.py` |
| Bestands-Browsertests rein mechanisch auf `/classic`, nicht abgeschwächt | PASS | `git diff tests/browser/*`: nur URL-Änderungen |
| Neue Route-/API-Verträge (Auth-Reihenfolge, `ok:false` ohne Schreibvorgang) | PASS | `tests/unit/test_ap22_web_routes.py` (21 Methoden) |
| Startseite (Guide, Karten, Neuanlage, Clone, Roots) | PASS | `tests/browser/test_ap22_home_ui.py`; Hooks per grep |
| Projektansicht (Held/Tabs/Kacheln/Board/Ausgabe/Assistent/Team) | PASS | `test_ap22_project_ui.py`, `test_ap22_work_ui.py`, `test_ap22_output_ui.py` |
| Projekteinstellungen → Git & GitHub: **alle zugesagten Aktionen** | FAIL | nur Repo/API-Felder + „Verbindung prüfen“ (`nova-project.js:507-532`); Testbericht `-mc.md:278` nennt GitHub ausdrücklich als nicht tief geprüft |
| Glocke: offene Fragen **+ blockierte Pakete + fehlgeschlagene Läufe** | FAIL | `nova-core.js:420-446` listet nur Fragen + laufende Läufe; Testbericht `:445-447` bestätigt die Lücke |
| Aktivität: Läufe mit **Öffnen/Stop**, Sessions, Fragen, **Zusammenfassungs-Kacheln** | FAIL | `nova-activity.js:101-107` nur Öffnen; keine Kacheln (`:82-91`); Testbericht `:442-444` |
| Agentenverwaltung: globale **und projektspezifische** Agenten bearbeiten | FAIL | Editor speichert/löscht/kopiert fest `scope=global` (`nova-agents.js:295-333, 406, 460, 478, 497, 512`); SPEC.md verlangt beides |
| Rotphase dokumentiert | PASS | beide Testberichte mit Verbatim-Auszügen |
| Validierungs-/Abschlussdokumentation | FAIL | `docs/features/AP22.md:405-408` Platzhalter (folgt mit dem Abschluss) |

## Befunde (Medium)

1. **[Medium] `bin/web/nova-project.js:507-532` — Git-&-GitHub-Bereich deckt die
   zugesagte Parität nicht ab.** Es fehlen Aktivierung, Token speichern/löschen,
   Branches, Pull/Push, Issues, Import und Merge-Request mit Bestätigung
   (zugesagt in AP22.md Paritätsmatrix; klassisch vollständig in
   `app.js:979-1088`). Gespeichert wird stets `enabled: !!github.enabled`,
   damit kann die Integration über die neue UI nie aktiviert werden.
   **Erforderlich:** Bereich funktional angleichen und je Aktion mit
   Browsertest samt Fehlerpfad belegen.
2. **[Medium] `bin/web/nova-core.js:420-446` — Glocke ignoriert zwei der drei
   vertraglichen Quellen.** Blockierte Pakete und fehlgeschlagene Läufe fehlen
   (Kommentar räumt das ein). **Erforderlich:** beide Quellen als verlinkte
   Einträge ergänzen und je Quelle einen Browsertest mit Badge-Zählung
   nachweisen.
3. **[Medium] `bin/web/nova-activity.js:101-107` — Laufzeile ohne Stop.**
   Vertrag fordert „je Projekt mit Öffnen/Stop“. **Erforderlich:** Stop-Knopf
   mit Bestätigung und `/api/stop`, im Browsertest abgedeckt.
4. **[Medium] `bin/web/nova-activity.js:82-91` — Zusammenfassungs-Kacheln
   fehlen vollständig.** **Erforderlich:** Kacheln mit stabilen DOM-Hooks,
   im Browsertest geprüft.
5. **[Medium] `bin/web/nova-agents.js:295-333` — Bearbeiten projektbezogener
   Agenten führt ins Leere oder auf den falschen Agenten.** Editor lädt und
   speichert fest `scope=global`; ein projektbezogener Agent schlägt fehl
   oder überschreibt bei Namensgleichheit den globalen Agenten. Das
   verletzt SPEC.md (globale und projektspezifische Agenten bearbeiten) und
   ist ein Korrektheitsrisiko. **Erforderlich:** Scope aus Route/Kontext
   übernehmen, Bearbeiten/Speichern/Löschen/Kopieren für den gewählten Scope
   sicherstellen, Browsertest für einen projektbezogenen Agenten.

## Befunde (Minor)

6. **[Minor] `docs/features/AP22.md:405-408`** — Validierungsabschnitt ist
   Platzhalter; folgt mit dem Abschluss (Koordinator).
7. **[Minor] `bin/web/nova-agents.js:106-110`** — Agentenkarte ohne
   Löschen-Knopf (Vertrag nennt „Bearbeiten/Löschen“); Löschen ist nur im
   Editor erreichbar. **Erforderlich:** Löschen-Knopf auf der Karte oder
   ausdrückliche Vertragsdokumentation der Abweichung.

## Verbleibende Risiken

Die genannten Lücken sind durch Code-Lesen und Testbericht-Selbstauskunft
belegt, nicht durch eigene Testläufe des Reviewers; für GitHub-, Glocken- und
Aktivitätsfeatures existieren keine tiefen Browsertests. Grünlauf-Nachweise
der Suiten stammen vom Koordinator (FremdNachweis).

## Nachfolge

Die fünf Medium-Befunde gehen in eine Paritäts-Fix-Runde (Testfirst durch den
unabhängigen Test-Agenten, Umsetzung durch den Coding-Agenten, erneute
Review-Prüfung). Das abschließende Urteil dieser Datei wird durch die
Folgerunde (`AP22-review-2.md`) mit `Verdict: PASS` quittiert, sobald die
Befunde behoben und belegt sind.

Verdict: CHANGES REQUIRED
