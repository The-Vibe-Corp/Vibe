# Review result — F34 (Abschlussreview)

> Prüfverlauf: Runde 1 (CHANGES REQUIRED, 1 High/3 Medium/2 Minor), Runde 2
> (Vorbericht, 5 Befunde), Runde 3 (CHANGES REQUIRED, 1 High/2 Medium/2 Minor),
> Runde 4 (CHANGES REQUIRED, 0 Critical/0 High/1 Medium/2 Minor), Runde 5
> (dieser Report). Jede Runde hat ihre Befunde am Folgestand nachgeprüft;
> die Nachprüfungstabellen der Runden 3–5 sind unten festgehalten. Der
> Reviewer führte in allen Runden keine eigenen Test-/Git-Läufe aus
> (read-only, Shell gesperrt); Testläufe sind als Koordinator-Nachweise
> deklariert und in `docs/features/F34.md` dokumentiert.

## Kurzfazit

Die drei Befunde meiner Runde 4 sind im Commit `5c67406` tatsächlich behoben:

1. **Karten-Rang-Badges:** Die Rangregel ist in `nvpRankMap` (`bin/web/nova-project.js:415–422`) vereinheitlicht und wird von Strip (`:477`), Speicherweg (`:497`) und Kartenbau (`:1810`) identisch genutzt. `nvpUpdateCardBadges` (`:426–448`) aktualisiert vorhandene Badges, ergänzt fehlende exakt an derselben DOM-Position wie der Kartenbau (`:216`, nach `.nv-ticket-id`) und entfernt Badges rangloser Karten. `saveOrder` (`:487–504`) ruft den Helfer nach dem lokalen Ränge-/Zähler-Nachzug auf; ein `NV.render()` findet dort nicht statt. Die drei früheren Kopien sind nachweislich ersetzt (keine weitere `P`-Rang-Berechnung im Modul).
2. **Vorlagen-Docstring:** `tests/browser/test_f34_activity_evals_ui.py:384` beschreibt jetzt den tatsächlichen Fall („Aktivität — Bereichsreihenfolge ohne Sitzungs-Hooks").
3. **MCP-Toggle-Vertrag:** `tests/browser/test_f34_settings_ui.py:1350–1418` prüft POST `{action:'toggle', name}`, Statuspille, Knopftext, Toast, den echten Render-Zähler (unverändert) und die Persistenz doppelt (GET `/api/mcp` **und** `opencode.json`). Das ist eine echte Verschärfung, keine Abschwächung.

Der neue Badge-Fall (`test_f34_project_ui.py:1596–1729`) ist scheiterbar: Ohne den Produktfix blieben die Badges nach dem ↓-Klick auf dem alten Stand `P1(F5)/P2(F8)/P3(B7)`, erwartet wird `P1(F8)/P2(F5)/P3(B7)` — der Fall muss dort rot sein. Er deckt Aktualisieren (3 vorhandene Badges) und Ergänzen (die übrigen offenen Karten erhalten nach dem Speichern Ränge) ab; der Entfernen-Zweig wird nur indirekt über `test_priority_reset` berührt.

Zwei Minor-Beobachtungen bleiben (Dokumentations-/Klarheitsgrad, keine funktionale Blockade): der Reset-Knopf der Priorisierung nutzt weiterhin `NV.render()` (zwischenzeitlich als benannte Abweichung in `docs/features/F34.md` dokumentiert) und der als „Endzustand" dokumentierte Browser-Inventurlauf (512 Fälle) ist durch den neuen Fall nicht mehr exakt der Endstand (in `F34.md` als Stand vor `5c67406` gekennzeichnet, der neue Fall separat nachgewiesen). Beide sind als Folgearbeit eingeordnet; es gibt keine Critical/High-Befunde.

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 2
- Verdict: PASS

Begründung des Verdicts (ausdrücklich): Es gibt keine Critical-/High-Befunde. Die beiden Minor-Punkte betreffen eine Klarheits-/Dokumentationsfrage und eine veraltete Endstandszahl; sie sind ohne Funktions-, Sicherheits- oder Datenrisiko und als Folgearbeit dokumentiert. Damit ist das Vertragsmuster „PASS ohne Critical/High" erfüllt; ich stufe bewusst nicht hoch, weil die Kernfixes nachweislich korrekt und die neuen Tests wirksam sind.

## Acceptance criteria

### WP1 — Shell, Benachrichtigungen, Rückfragen, Suche/Combobox

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Genau eine Benachrichtigungssammlung (Glocke) + Peek `#nv-toasts`; Einträge einzeln schließbar; „Alle als gelesen"; Erklärung übersetzt/kompakt | PASS | `bin/web/nova-core.js:522–800` (Panel/Einträge), `:673` (`nv-dismissed-live`), `:729–775` (Live-Einträge) | `tests/browser/test_f34_shell_ui.py:402,432,455,529,578`; `f34-browser-final2.log` (512 Fälle, 6 FAIL/1 ERROR = die sieben dokumentierten vorbelasteten Fälle) |
| Statische Sidebar entfällt; fünf Kopf-Navigationspunkte; Kontext-Panel per Escape/Scrim schließbar | PASS | `bin/web/index.html` (Sidebar-Entfall/Nav), `bin/web/nova-core.js:515,968` | `tests/browser/test_f34_shell_ui.py:610,639`; `tests/browser/test_ap22_project_ui.py` (Umstellung auf `nav[data-nv-navs]`, Diff geprüft) |
| Suche/Filter-Bausteine; kein nacktes `input[type=search]` | PASS | `bin/web/nova-core.js:992` (`NV.search`) | `tests/browser/test_f34_shell_ui.py:679` |
| Combobox API-kompatibel, Placeholder/Lupe, Listengrößen | PASS | `bin/web/nova-widgets.js` (`NV.combobox`) | `tests/browser/test_f34_shell_ui.py:707` |
| Zentrale Rückfragen: Banner, Kopfzähler, Postfach, gemeinsame Karte, 5-s-Poll, Seen-Schutz | PASS | `bin/web/nova-core.js:494–520,808–860`; `bin/web/nova-widgets.js:168–240` | `tests/browser/test_f34_questions_ui.py:416–786` (17 Fälle) |
| Neue Frage → Glocken-Eintrag mit Postfach-Knopf, keine tote Route | PASS | `nova-core.js:744–748` (Knopf), `:884–887` (kein `href`) | `test_f34_questions_ui.py:687–782` (verbietet zusätzlich jeden Link im Eintrag) |

### WP2 — Startseite und Agenten

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Startseite: Suchzeile + Trefferzahl; Pin-Raster; angeheftete Karten raus aus der Normalliste | PASS | `bin/web/nova-home.js:46–47,66–67` | `tests/browser/test_f34_home_agents_ui.py:366–542` |
| Agenten: Suche + „Neuer Agent" in Toolbar; Tag-Filter über der Liste, UND-Verknüpfung | PASS | `bin/web/nova-agents.js:133–144,237` | `tests/browser/test_f34_home_agents_ui.py:588,617` |
| Agentenkarte zweizeilig, Pin nur Symbol mit `aria-label`, Meta umbricht | PASS | `bin/web/nova-agents.js:287–298` | `tests/browser/test_f34_home_agents_ui.py:674,737` |

### WP3 — Aktivität und Auswertungen

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Reihenfolge Kacheln → Rückfragen → Läufe; Sessions-/Limit-Hooks entfallen; Hinweis mit Projektlink | PASS | `bin/web/nova-activity.js:35–57` | `tests/browser/test_f34_activity_evals_ui.py:383,418` |
| Laufzeilen mit Projekt, Zustand, „Öffnen", Stopp | PASS | `bin/web/nova-activity.js:96` | `tests/browser/test_f34_activity_evals_ui.py:433` |
| Tabs/Routing `#/evaluations/<tab>` | PASS | `bin/web/nova-evals.js:703–712` | `tests/browser/test_f34_activity_evals_ui.py:822` |
| Kosten: Summen, Projekttabelle, Detail, Preislink, Editor, EUR/USD, Leerzustand | PASS | `bin/web/nova-evals.js:129–134,270` | `tests/browser/test_f34_activity_evals_ui.py:516–668` |
| Läufe: Tabelle, Suche/Status, Prune/Cleanup | PASS | `bin/web/nova-evals.js:506` | `tests/browser/test_f34_activity_evals_ui.py:696` |
| Umgebung: Doctor/Pfade/Harness; Fritzbox nur bei Automatik | PASS | `bin/web/nova-evals.js:597` | `tests/browser/test_f34_activity_evals_ui.py:749–791` |

### WP4 — Einstellungen

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Lokale Navigation + Sektionsreihenfolge `global-agents … harness` | PASS | `bin/web/nova-settings.js:99–106` | `tests/browser/test_f34_settings_ui.py:544,840` |
| Globale AGENTS.md oben, einklappbar, `rows ≥ 16`, Vorlage nur bei fehlender Datei, Speichern ohne Voll-Neurender | PASS | `bin/web/nova-settings.js:165–175` | `tests/browser/test_f34_settings_ui.py:544–629` |
| Darstellung: Akzent-Swatches statt `<select>`, Währung EUR/USD + `usd_rate` | PASS | `bin/web/nova-settings.js:237–296` | `tests/browser/test_f34_settings_ui.py:675,744` |
| Limits als zwei erklärte Optionskarten mit hervorgehobenem Modus | PASS | `bin/web/nova-settings.js` (Limits-Block) | `tests/browser/test_f34_settings_ui.py:885` |
| Gates: Projektauswahl, Tabelle, Origin, Overrides, ein Sammel-POST, Reset nur mit Projekt | PASS | `bin/web/nova-settings.js:509–571` | `tests/browser/test_f34_settings_ui.py:931–1210` |
| Modelle/Katalog/Profile | PASS | `bin/web/nova-settings.js:699,759–797` | `tests/browser/test_f34_settings_ui.py:1254,1297` |
| MCP: Karten, Statuspille, Toggle nur Karte + Toast, Bearbeiten im Kontext-Panel, Scope, Suche | PASS | `bin/web/nova-settings.js:891–960` | `tests/browser/test_f34_settings_ui.py:1325–1418` |
| Entfernt: Kosten, Run-Register, Umgebung, Fritzbox, Emulator, opencode-Server | PASS | `bin/web/nova-settings.js` (Sektionsliste) | `tests/browser/test_f34_settings_ui.py:813` (Abwesenheitsprüfung) |

### WP5 — Projektdetail

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Überblick: Autonom-Karte oben; Kacheln inkl. Entwurf; keine Feedback-/Ohne-Nachweis-Kachel; „ohne Nachweis" als Badge | PASS | `bin/web/nova-project.js` (Überblick) | `tests/browser/test_f34_project_ui.py:890,928`; `test_ap22_project_ui.py` (Removed-Tiles + `[data-nv-proof]`) |
| Zustand-Karte (letztes Paket) + Sessions-Zeilen mit fester Resume-Spalte; Limit nur in Einstellungen | PASS | `bin/web/nova-project.js:1762–1774` | `tests/browser/test_f34_project_ui.py:957,993,1060` |
| Arbeit: Aktionsleiste → Filter → Priorisierung → Liste; kein Board; Suche findet auch Erledigte | PASS | `bin/web/nova-project.js:1776–1844` | `tests/browser/test_f34_project_ui.py:1076–1267` |
| Priorisierung: Strip, Drag & Drop mit Vorschau, ↑/↓, konsistente Ränge (Strip + Karten-Badges), kein Voll-Neurender beim Speichern | PASS (Reset: benannte Ausnahme, siehe Findings) | `bin/web/nova-project.js:415–448,454–620,1810–1819` | `tests/browser/test_f34_project_ui.py:1311–1760`; neuer Fall `:1596–1729` |
| Beschreibung: `rows ≥ 6`, keine Status-Pillen, Guide-Navigation | PASS | `bin/web/nova-project.js:1857–1858` | `tests/browser/test_f34_project_ui.py:1803–1868` |
| Einstellungen: Reihenfolge, AGENTS-Backups, Basics, Sandbox, Team, GitHub-Blöcke, Rechte, Limit, Emulator nur Android; Prüfungen/Sessions/opencode/Fritz entfernt | PASS | `bin/web/nova-project.js:1860–1876` | `tests/browser/test_f34_project_ui.py:1896–2178` |

### WP6 — Ausgabe

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Kopfzusammenfassung Haupt/Subs, klickbar zum Fokussieren | PASS | `bin/web/nova-output.js:164–217` | `tests/browser/test_f34_output_ui.py:386,452` |
| Zusammenfassung scrollt horizontal, nicht die Seite | PASS | `bin/web/nova-output.js` (Summary-Scroll) | `tests/browser/test_f34_output_ui.py:484` |
| Hauptkarte: Fokus-Knopf, Log 60 vh mit eigenem Scroll, „Alles anzeigen" | PASS | `bin/web/nova-output.js:201–217` | `tests/browser/test_f34_output_ui.py:523,577` |
| Subagenten-Raster (2 Spalten ab 1200 px), Log 40 vh + Aufklappen | PASS | `bin/web/nova-output.js:428–435` | `tests/browser/test_f34_output_ui.py:627–730` |
| Steuerblock mit Fortsetzen-Kontext/Resume; keine horizontalen Überläufe | PASS | `bin/web/nova-output.js:242,284` | `tests/browser/test_f34_output_ui.py:764–915` |

### WP7 — Backend

| Criterion | Status | Implementation (file:line) | Test / Evidence |
|---|---|---|---|
| Löschschutz abgeschlossener Pakete/Feedback (`ValueError`, API `ok:false`) | PASS | `bin/vibe:783–811` | `tests/unit/test_f34_backend.py:434,453,469`; `tests/unit/test_feedback_completed.py` |
| Projektlimit + `session_overview(project)` + `POST/GET /api/sessions` | PASS | `bin/vibe_runs.py:1011–1149` | `tests/unit/test_f34_backend.py:517,534` |
| Gates gesammelt: Validierung zuerst, `null` entfernt Override, Antwort mit `defaults/overrides/global/origin`; Einzel-POST bleibt | PASS | `bin/vibe_gates.py:206–263` | `tests/unit/test_f34_backend.py:567–624` |
| Kosten: `month`, `months`, `monthly` additiv | PASS | `bin/vibe:5583–5700` | `tests/unit/test_f34_backend.py:791,811` |
| Währung `currency`/`usd_rate` strikt (0.01..100), atomar | PASS | `bin/vibe_ui_config.py:61–66,146–180` | `tests/unit/test_f34_backend.py:655,681` |
| Run-Cleanup `{removed, remaining}`, `prune` unverändert | PASS | `bin/vibe_runs.py:856` | `tests/unit/test_f34_backend.py:835,859` |
| `nova-evals.js` in `STATIC_FILES`, `WEB_FILES`, Import-Manifest | PASS | `bin/vibe-web.py:2523–2538`; `scripts/setup-vibe.py:75`; `docs/import-manifest.json:1340,1503` | `tests/unit/test_f34_backend.py:888,901` |
| Meldungen deutsch/verständlich/ohne Geheimnisse | PASS (Stichprobe) | `bin/vibe:786–811`, `bin/vibe_ui_config.py:155–161` | Keine gegenteilige Fundstelle in den geprüften Bereichen |

### Ticket- und Abschlussabdeckung

| Criterion | Status | Implementation / Dokument | Test / Evidence |
|---|---|---|---|
| FEEDBACK.md F34 auf `[x]` mit `Commit:`/`Test:` | nachgelagert (mit dem Abschluss-Commit) | `FEEDBACK.md` F34 | Koordinator setzt Häkchen und Nachweis mit dem finalen Commit |
| F34.md Status | PASS | `docs/features/F34.md:3` „Abgeschlossen (Review PASS)" | dieser Report |
| Trilium-Dokumentation | nachgelagert | Trilium-Notiz `tA1ljzUxrbnK` | Finalisierung mit dem Abschluss-Commit |

## Nachprüfung der Befunde aus den Runden 3–5

| Runde | Befund | Urteil | Beleg |
|---|---|---|---|
| R3 | [High] Render-Zähler existierte nicht; „kein Voll-Neurender" waren Tautologien; Gates-Fall ohne echte POST-/Wertprüfung | ERLEDIGT | `test_f34_project_ui.py:690–754`, `test_f34_settings_ui.py:415–481` (Selbstabsicherung, Scheitern ohne Installation); Gates: genau ein POST, Vollvergleich der Wertemap, Zähler unverändert |
| R3 | [Medium] `saveOrder` rief `NV.render()` | ERLEDIGT | `nova-project.js:487–504` — kein NV.render, Ränge/Zähltext lokal, `draw()` |
| R3 | [Medium] Abnahme-Zahlen widersprüchlich | ERLEDIGT | `docs/features/F34.md` — alle Summen nachgerechnet (27+53=80, 36+71=107, 53+60=113, 33 behoben benannt, 6+1=7) |
| R3 | [Minor] tote Route im Benachrichtigungs-Datenfeld | ERLEDIGT | `nova-core.js:884–887`; `test_f34_questions_ui.py:754–757` |
| R3 | [Minor] ap22_activity-Zähler akzeptierte fehlenden Zähler | ERLEDIGT | `test_ap22_activity_ui.py:847–862` |
| R4 | [Medium] Karten-Rang-Badges nach Prioritätsaktionen veraltet | ERLEDIGT | `nvpRankMap`/`nvpUpdateCardBadges` (`nova-project.js:415–448,497–500`); Fall `test_f34_project_ui.py:1596–1729`, Rot-Nachweis gegen Stand ohne Fix |
| R4 | [Minor] Vorlagen-Docstring in `test_f34_activity_evals_ui.py` | ERLEDIGT | `:384` beschreibt den tatsächlichen Fall |
| R4 | [Minor] MCP-Toggle-Vertrag ohne Testnachweis | ERLEDIGT | `test_f34_settings_ui.py:1350–1418` (POST, Pille, Text, Toast, Zähler, doppelte Persistenz) |
| R4 | Fallzahl-Differenz 2523 → 2540 unerklärt | ERLEDIGT | `F34.md`: neue Backend-Suite `test_f34_backend.py` (17 Fälle) |
| R4/R5 | [Minor] Reset der Priorisierung mit `NV.render()` | ALS BENANNTE ABWEICHUNG DOKUMENTIERT | `F34.md` WP5/Arbeit: Reset folgt der serverseitigen Standardordnung; Voll-Neurender bewusst |
| R4/R5 | [Minor] Browser-Endstandzahl um einen Fall veraltet | BEREINIGT | `F34.md`: Inventurlauf als Stand vor `5c67406` gekennzeichnet, Badge-Fall separat nachgewiesen (34/34, zweimal) |

## Findings

- [Minor] `bin/web/nova-project.js:506–516` — Reset der Priorisierung nutzt `NV.render()` (benannte Abweichung, dokumentiert in `docs/features/F34.md` WP5/Arbeit). Funktionale Auswirkung: ein bewusster Voll-Neurender, weil die Reihenfolge serverseitig neu bestimmt wird. Folgearbeit: lokales Neuzeichnen aus der POST-Antwort oder ausdrückliche Vertragsformulierung.
- [Minor] `docs/features/F34.md` — die 512-Fälle-Inventur ist als Stand vor `5c67406` gekennzeichnet; der Badge-Fall ist separat nachgewiesen (Projekt-Suite 34/34, zweimal, mit Rot-Nachweis). Folgearbeit: eine spätere Gesamtinventur zieht die Fallzahl nach.

## Verification

- Change set reviewed: `a1932ee^..HEAD` (Diff-Datei, 23.859 Zeilen, 35 Commits) plus vollständige Dateilesungen im Worktree; HEAD über die Git-Administrationsdateien bestätigt.
- Git commands run by me: keine — Shell in den Review-Sitzungen gesperrt (read-only-Rolle), hier offengelegt. Keine Dateien verändert.
- Checks with supplied output (gelesene Protokolle): Browser-Inventur 512 Fälle / 7 vorbelastete Rote; Unit-Gate-Lauf 2540 Fälle / 80 Rote; Vor-F34-Kontrolllauf 2523 Fälle / 107 Rote; Projekt-Suite 34/34 nach `5c67406` (Koordinatorangabe, Rot-Nachweis des Badge-Falls von Test- und Koordinatorseite dokumentiert).
- Abschwächungs-Stichprobe `5c67406`: Produktdatei = Vereinheitlichung der Rangregel plus lokaler Badge-Nachzug, keine entfernte Funktion; Testdateien = neue Methode, erweiterter MCP-Fall (nur strengere Zusicherungen), korrigierter Docstring; keine entfernten Testmethoden. Keine Abschwächung gefunden.
- Checks not independently run: alle Test-, Build-, Lint- und Verify-Läufe (read-only-Rolle).
- Remaining risks: Testherkunft aus dem Repository nicht belegbar (Sitzungsangaben); Entfernen-Zweig von `nvpUpdateCardBadges` nur indirekt über Reset gedeckt; Trilium-Finalisierung und Ticket-Häkchen werden mit dem Abschluss-Commit gesetzt.

## Nicht geprüft

- Eigene Test-/Build-/Verify-Läufe (Shell gesperrt; alle Ergebnisse sind Koordinator-Nachweise mit Protokollen).
- `git status`/Arbeitsbaum-Sauberkeit; Manifest-Neuberechnung über die statische Zuordnung hinaus.
- Visuelle Abnahme (Layout, Bruchstellen, Responsive) — nur Code- und Testprüfung.
