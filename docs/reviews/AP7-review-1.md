# AP7 Review — Runde 1

Reviewer: code-reviewer (unabhängig, read-only)
Datum: 2026-11-10
Grundlage: Ausgangsstand `28cf66d` → Arbeitsbaum (uncommitted), Ticket AP7
(TICKETS.md:693), docs/features/AP7.md, docs/reviews/AP7-test-agent-report.md,
tests/browser/test_ap7_settings_ui.py, bin/web/app.js, bin/web/styles.css,
docs/import-manifest.json.

Die Antwort des Reviewers wird unverändert wiedergegeben:

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 3
- Verdict: CHANGES REQUIRED

**Zentrale Einschränkung vorab:** Alle Shell-/Git-Befehle wurden von der Berechtigungsprüfung zurückgewiesen (`Permission denied: shell`, insgesamt 4 Versuche); es existiert kein Git-Tool im Tool-Katalog. Ich konnte daher **keinen einzigen Git-Befehl** ausführen (`git status`, `git diff 28cf66d`, `git show`), keinen Syntax-/Manifest-/Testlauf nachrechnen (node --check, check-syntax.py, check-import-manifest.py, unittest) und die Prüfsummen im Manifest nicht selbst berechnen. Alle Test- und Prüfergebnisse sind damit **Agent-Angaben**, nicht von mir ausgeführt. Geprüft habe ich stattdessen vollständig lesend: Implementierung, alle fünf Testdateien, Backend-JSON-Verträge, Manifest, Doku, Test-Agent-Report, Screenshot (als Bild gelesen) und die Trilium-Notiz (per MCP-Lesung).

## Nachrechnungen / eigene Prüfungen (tatsächlich ausgeführt)
1. **Screenshot `docs/features/F13-einstellungen.png` gelesen (Bild direkt betrachtet):** bestätigt die neue Struktur — Abschnittsleiste („Agenten · 0 aktiv“, „Schreibrechte · Standardliste“, „Sandbox · aus“, „Git & GitHub · aus“), offener Agenten-Abschnitt, drei eingeklappte Abschnitte, keine Ladezeile. Der behauptete Standardzustand ist damit **unabhängig belegt** (bei 1400×1000 vh der Testvariante).
2. **Trilium vom MCP-Server gelesen:** Notiz `vDzuhFgjY4PV` existiert („AP7 Einstellungs-UI neu aufgebaut“, Geändert: 2026-11-10, Labels #project=vibe, #arbeitspaket=AP7) — stimmt mit docs/features/AP7.md:156 und docs/trilium-index.md:55 exakt überein.
3. **Backend-Feldverträge lesend verifiziert:** `write_dirs_error` (vibe_services.py:102,105), `write_dirs_custom` (vibe_services.py:107), `sandbox` inkl. Fallback (vibe_services.py:109–120), `github` mit `enabled/repo/label/api/remotes/branch/ahead/behind/unpushed` (vibe_github.py:294–304) — die Chip-Ableitung app.js:183–186 liest nur Felder, die in `project_detail` garantiert gesetzt werden. Kein Phantom-Feld.
4. **Testlogik der neuen Suite (575 Zeilen) vollständig gelesen:** echte Assertions, keine leeren Tests, keine Skip-Marker, `assertNotIn`/`assertFalse`-Muster in den Bestandstests intakt; Helfer `expand_optional` ist in allen vier Dateien neutral (No-op ohne `> summary`, keine Abschwächung).
5. **TESTER-Konfiguration:** `.vibe/project.env:12` = `TESTER=test-agent` — verbindliche Test-Agent-Regel erfüllt; Konfigurationsänderungen an Testdateien stammen laut Report vom Test-Agenten (Coding-Agent darf keine Tests ändern — konsistent mit der Berichtslage).

## Acceptance criteria
| Kriterium | Status | Implementierung (file:line) | Test / Evidence |
|---|---|---|---|
| Einstellungs-UI zusammen neu gegliedert (zugänglich) | PASS* | bin/web/app.js:172–208 | Test-Agent-Red-Protokoll (docs/reviews/AP7-test-agent-report.md:28–104) + 5/5 grün laut Agent (nicht von mir ausgeführt) |
| Wichtiges oben: Agenten-Abschnitt offen an erster Stelle | PASS | app.js:206–208 (Reihenfolge nav → `#project-agents` → drei `<details>`) | test_ap7_settings_ui.py:327–334 (DOM-Reihenfolge) + Screenshot von mir verifiziert |
| Optionales ausgeblendet (Klapppunkte, Statuspillen ohne Aufklappen) | PASS | app.js:176–178, 202–204; CSS bin/web/styles.css:65–77 | test_ap7_settings_ui.py:303–325; Screenshot bestätigt |
| Standardzustand ohne Scrollen | PASS* | app.js:206–208 + CSS `.settingsstack` | test:336–344 (nur Leiste/Agentensteuerung in vh 1000); Screenshot belegt ganzen Standardzustand auf einer Bildschirmhöhe |
| GitHub-Aktionen/Issues-Block nur bei aktiver Verknüpfung | PASS | app.js:650–662 (`actions=active?...:null`) | test:402–494 (getestete Reihenfolge mit Cleanup am Testende „für Reihenfolgenunabhängigkeit“) |
| Stabilitätskontrakte (Tab-Name, #panel-einstellungen, #project-agents/#sandbox/#github, Button-/Labeltexte) | PASS | app.js:98, 150, 203–204, 566–663 | Bestandstests ohne fachliche Änderungen übernommen, nur Aufklapp-Helfer; Bestandssuiten laut Agent 8-Suite-Runs grün |
| Tastaturbedienbarkeit / Fokusreihenfolge | PASS | native `<button>`/`<summary>`, keine tabindex-Hacks (app.js:194–198) | test:534–600 (Erste-Fokus- und Tab-Reihenfolge über `data-goto`) |
| Manifest nachgeführt mit Begründung | PASS* | docs/import-manifest.json:902–909 (AP7-Eintrag app.js + styles.css, Resync-Begründung in-text) | Agent: verify.sh quick Exit 0; Prüfsummen von mir nicht nachrechenbar |
| Fachliche/technische Doku + Trilium | PASS | docs/features/AP7.md (vollständig, deckungsgleich mit Code) | Trilium-Notiz von mir direkt verifiziert (s. o.) |

\* = Implementierung von mir unabhängig geprüft (Lesesatz + Screenshot), Test**ausführung** nur Agent-mitgeteilt (Shell verweigert).

## DoD-Kriterien
| DoD | Status |
|---|---|
| Ticket-AC erfüllt | ✓ (Implementierung, Screenshot, Testlogik geprüft; Testlauf agent-nachgeliefert) |
| Tests vom unabhängigen Test-Agenten | ✓ TESTER konfiguriert, Rot-Grün-Protokoll plausibel (Red-Fehlerursachen stimmen mit Bestandscode überein), Helfer neutral |
| Verbindliche Prüfungen | ✗/△ Agent meldet quick Exit 0 und 5/5-Runs; **von mir nicht nachrechenbar** (Berechtigungen). full-Discovery bleibt vorbestehend rot, Baseline-Vergleich sauber argumentiert (Manifest-Defekt am Ausgangsstand erklärt die 2 zusätzlichen Baseline-Failures) |
| Doku + Trilium | ✓ Feature-Doku fachlich stimmig; Trilium verifiziert; eine toten-Verweis-Frage (Minor 4) |
| Unabhängiger Review | diese runde |

## Findings
- [Medium] `bin/web/app.js:199` — Chip-Sprungland liegt unter der fixen Kopfleiste
  - Evidence: `sec.scrollIntoView({block:'start'})` richtet die Zielsektion an die Scrollport-obere Kante. Die Kopf- beziehungsweise Detailtitelleiste ist fixiert (`bin/web/styles.css:78` `.detailbar{position:sticky;top:0;z-index:60;background:var(--bg)}`, F13-Bestand) und überdeckt den Bereich; im gesamten `bin/web` existiert weder `scroll-margin` noch `scroll-padding` (Grep-verifiziert). Bei gerundet ≈54px Kopfhöhe wird der `<summary>` (≈45px) des Zielsections vollständig versteckt; nach Chip-Klick erscheint der Abschnitt unbetitelt und „der Klickgrund“ (Titel) ist nicht sichtbar — der Nutzer muss nachrollen, obwohl der Chip den Abschnitt sichtbar anspringen soll. Der AP7-Test prüft nur die Begrenzungsrahmenfunktion (`top >= 0`, `bottom <= viewport`, test_ap7_settings_ui.py:210–228) und maskiert die Überdeckung. Statisch aus Quellordner CSS/DOM schlüssig; **runtime-Überprüfung von mir nicht möglich** (Shell verweigert).
  - Required fix: `scroll-margin-top` in Kopfleistenhöhe für `.seccard` und `#project-agents` (oder `scroll-padding-top` am Scroll-Root) setzen; den AP7-Browsertest um eine Überdeckungsanalyse erweitern, dass der `<summary>`-Mittelpunkt nach dem Chip-Klick nicht unter `.detailbar` liegt (z. B. `elementFromPoint`- oder Begrenzungsrahmenversatz zur Kopfhöhe).
- [Minor] `bin/web/app.js:183` vs `bin/web/app.js:583–584` — Sandbox-Zustandsableitung doppelt
  - Evidence: Zeile ist exakt dieselbe Fachregel „aus | Fehler | bubblewrap fehlt | Werkzeuge fehlen | bereit“ in zwei Auswertungen; künftig riskieren die beiden Stellen auseinanderzulaufen. (Auch der `rechte`-Zustand wird hier erneut, das ist verständlich genug.)
  - Required fix: kleine, benannte Hilfsfunktion für den Sandbox-Zustandsstring herausziehen; Schreib-API unverändert halten.
- [Minor] `bin/web/app.js:200–201,245` — Agenten-Chip bleibt bei Lauffehler dauerhaft auf „…“
  - Evidence: `load().catch(...)` zeigt den Fehler nur in der Karte, `onCount` wird dann nie gerufen; die Leiste bleibt auf „…“ mit Ruheton mut statt berichtendem Fehlerzustand (Widerspruch zum selbsterklärten Fehler-Muster der anderen Chips `d.write_dirs_error` → „Fehler“).
  - Required fix: im Fehlerpfad die Pill auf einen erkennbaren Text/Ton setzen oder die Karte selbstständig aus d. Agenten-Fehlernachricht berichten (Implementierungseher-Ermessensbrief; die UI-Sprache muss laut Backend-Feldern sachgerecht bleiben).
- [Minor] `docs/features/AP7.md:148` — Verweis auf `docs/reviews/AP7-review-1.md` ins Nichtexistent
  - Evidence: `docs/reviews/` enthält aktuell nur `AP7-test-agent-report.md` (Glob-verifiziert). Falls der Verweis auf diese Reviewrunde vorgreift: die angekündigten Baseline-Vergleichsdetails müssen tatsächlich in der gespeicherten Review-Datei stehen, sonst ist es ein hängender Verweis.
  - Required fix: Verweis nur beibehalten, wenn die genannten Baseline-Vergleichs-Befunde tatsächlich in `docs/reviews/AP7-review-1.md` landen; ansonsten den Verweis auf die tatsächliche Nachweisstelle korrigieren.

## Verification
- Change set reviewed: Ausgangsstand `28cf66d` → Arbeitsbaum. **`git status`/`git diff` konnte ich nicht ausführen** („Permission denied: shell“ in jedem Versuch; alternativer Git-Zugang fehlt im Katalog). Geprüft habe ich vollständig: bin/web/app.js (settingsPanel, projectAgentsCard, rightsBody, sandboxBody, githubBody, tabPanel/Detail-Tabs), bin/web/styles.css, bin/vibe_services.py:88–129, bin/vibe_github.py:282–336, docs/import-manifest.json (AP7-Teilabschnitt), docs/features/AP7.md, docs/reviews/AP7-test-agent-report.md, TICKETS.md:693–698, tests/browser/test_ap7_settings_ui.py (komplett) und die Helferbereiche der fünf Änderungen-Testdateien, .vibe/project.env.
- Git-Befehle ausgeführt von mir: **keine** (werden durch Berechtigungen verweigert).
- Prüfungen mit mitgelieferten Objekten von mir direkt belegt: Screenshot-Inhalt (F13-einstellungen.png lesend geprüft), Trilium-Notiz (resolve + Labels), Backend-Feldverträge, Rot-Protokoll-Plausibilität (Red-Fehlerursachen stimmen mit Bestandcode).
- Prüfungen NICHT unabhängig ausgeführt: **alle** Build-/Test-/Statikprüfungen — `node --check bin/web/app.js`, `python3 scripts/check-syntax.py`, `python3 scripts/check-import-manifest.py` (Prüfsummen!), `python3 -m unittest` (der ok ist: AP7-Suite und betroffene Browser-Suiten grün fast alle Bedingungen), `bash scripts/verify.sh quick/full`. Diese Ergebnisse sind ausschließlich Agent-Angaben. Auch die Behauptung, Testdateien seien nur durch Helfer-Schritte verändert, konnte ich **ohne Diff nicht endgültig beweisen** (nur Lesen des Ist-Stands).
- Wichtig geprüfte Bereiche: Chip-Leiste/Klappstruktur, GitHub-seitige Fazibilität, Stabilitätskontrakte, Manifest/Resync, Testintegrität, DoD.
- Remaining risks: Deltas/Änderungsgrenzen gegenüber `28cf66d` und etwaige Fremdänderungen im Arbeitsbaum sind von mir unbestätigt (kein Git-Zugang); die Browser-Tests sind gegen die bestehende Sticky-Kopf­leiste nicht Überdeckungssicher (Medium 1); Discovery `full` bleibt umgebungsbedingt rot — der Agent vergleicht nur Fehlermengen gegen Baseline, dunkle Zähl-Deltas wären hier Teil des Risikos, allerdings plausibel erhärtet.

**Verdict: CHANGES REQUIRED** — zu beheben:
1. [Medium] Sprungziel-Überdeckung durch die fixe Kopfleiste (`scroll-margin-top` bzw. `scroll-padding-top`) im AP7-Umfang beheben und Browser-Test gegen Überdeckung sichern.
2. [Minor] Aufräumarbeiten: Sandbox-Zustandsableitung entdoppeln, Agenten-Chip-Fehlerzustand, Verweis auf `docs/reviews/AP7-review-1.md` auflösen oder mit Inhalt belegen.
3. Nach dem Fix die AP7-Testsuite und die betroffenen Bestands­suiten erneut laufen lassen und die (agent-nachgelieferten) Ergebnisse mit den Dokuaufnahmen abgleichen; danach erneuter Review.
