# Review F24 — Runde 1

Independent Reviewer: code-reviewer (Session ses_e44b419d6ffeyE9As6gPfXdvUH).
Ausgangscommit: `5f13220`, Branch `vibe/vibe-F24-1794139598747889668-2696346-28951`.
Review-Grundlage: Full-Diff `/tmp/opencode/f24-full-diff.txt` (-U20), neue Dateien und Arbeitsbaum; Shell-/Git-Zugriff war im Reviewkontext verweigert.

Nachfolgend das unveränderte Reviewergebnis des Reviewers:

---

Ich habe den kompletten Review auf read-only-Basis durchgeführt. Shell/Git-Zugriffe wurden im Review-Kontext verweigert (Permission denied), daher habe ich den bereitgestellten Full-Diff (`/tmp/opencode/f24-full-diff.txt`), alle neuen Dateien und die relevanten Originalquellen im Arbeitsbaum direkt gelesen und gegen `bin/vibe_runs.py`, `bin/vibe-web.py` (Endpoint + `run_is_active`/`subagents_of`) und die F13-Browsertests (ganzseitige `tablist.count()==1`-Assertion in `test_project_detail_ui.py:163-164`) abgeglichen.

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 3
- Verdict: CHANGES REQUIRED

## Acceptance criteria

Das Ticket (FEEDBACK.md F291, Eintrag F24) ergibt fünf fachliche Kriterien:

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Aktiven Agenten in der Ausgabemaske anzeigen | PASS | `bin/vibe-web.py:514-521` (Feld `agent` nur bei LIVE-Registerstand), `bin/web/app.js:352-359` (Pill `#agent-active`, „—" ohne Lauf) | `tests/unit/test_f24_output_agent_ui.py` (5 Tests, 2 auch Negativfälle ohne Agentenname); `tests/browser/test_f24_output_tabs_ui.py:307-339` (sichtbar bei Lauf, weg nach `finished`) — Ausführung nur übernommen, nicht selbst gelaufen |
| Subagenten-Aufruf: Ausgabe des Subagenten anzeigen | PASS | `bin/web/app.js:399-411` (Tab → Pane → `/api/subagent-output`), `bin/vibe-web.py:525-556` unverändert nutzbar | `tests/browser/test_f24_output_tabs_ui.py:381-405` (Klick auf Sub-Tab zeigt „Ausgabe A"; kein pageerror) |
| Mehrere parallele Agenten → mehrere Tabs; nur aktiver Tab aktiv; Wechsel lädt nach | PASS | Tabs: `bin/web/app.js:416-443` (sync/remove/Tabliste nur bei `running && subs>0`); Nachladen: `bin/web/app.js:361-378` (`hold`/`logBuf` für den Haupt-Stream, `flush` bei `showMain`), `bin/web/app.js:441` (Refresh des aktiven Sub-Tabs je Poll) | `tests/browser/test_f24_output_tabs_ui.py:350-405` (Tabliste, genau ein `aria-selected`, Ausgabewechsel, Rückwechsel `HAUPT-4711`) |
| Tab schließt sich, wenn der Agent fertig ist | PASS | `bin/web/app.js:437-438` (Tabs ohne laufenden Subagenten entfernt; Rückfall auf Hauptagent); Tabs nur für `status==='running'` (421) | `tests/browser/test_f24_output_tabs_ui.py:407-449` (Tab nach `completed` verschwunden, Tabliste danach ganz weg) |
| Nur ein Agent → keine Tabs, aktiver Agent im Ausgabebereich | PASS | `bin/web/app.js:379-427` (Tabliste nur gemountet bei Mehrfachlage; sonst unmount/fallbackToMain) | `tests/browser/test_f24_output_tabs_ui.py` (Test d: Übergang zum Einzelagenten ohne Tabliste); kein eigener Einzelagenten-Fall mit direkter Tablisten-Freiheits-Assertion, indirekt aber abgedeckt |

Nachweisintegrität: Rote Phase (3/5 Unit, 4/4 Browser failed vor Implementierung) ist laut Arbeitspaket durch den Test-Agenten belegt; ich kann das ohne Git/Shell nicht unabhängig belegen — Stand unten (Verifikation). Keine leeren Testkörper, keine unmöglichen Assertions gefunden; die Browser-Tests fahren den echten Server mit echtem Register-Tool (`bin/vibe_runs.py start`) und echtem Dashboard-SSE, keine Attrappen des Fachverhaltens. Keine Statements, die nicht scheitern können; keine Skip-Marker.

## Findings

- [Medium] `bin/web/app.js:394-398` — Tastaturbedienung der Agent-Tabs ist fehlerhaft (ArrowLeft/ArrowRight/Home ohne Wirkung)
  - Evidence: Der Handler vermischt Schlüssel und Index: `if(e.key==='ArrowRight')n=keys[(i+1)%keys.length]` weist `n` bereits den nächsten Tab-Schlüssel (String) zu, danach wird `choose(keys[n])` aufgerufen — `keys[<string>]` ist `undefined`, `choose(undefined)` bricht in `tabs.get(key)→return` sofort ab. Gleiches gilt für `Home` (`n=keys[0]` ist der String `'main'`). Nur `End` funktioniert, weil dort `n` ein numerischer Index ist (Inkonsistenz derselben Variablen). Folge: Die in `docs/features/F24.md:105` ausdrücklich beschriebene „Tastaturbedienung (Pfeile, Home/End)" funktioniert für Pfeile und Home überhaupt nicht; die frisch implementierte Zugänglichkeit ist nicht erreichbar, und es existiert kein Test, der den Defekt erwischt hätte.
  - Required fix: Keyboard-Handler einheitlich über Array-Index umsetzen (Zielindex berechnen, dann `choose(keys[index])`) und vom Test-Agenten einen Tastatur-Testfall (ArrowLeft/Right/Home/End) anfordern und ausführen; vorherigen Zustand in der Feature-Doku korrigieren.

- [Minor] `bin/web/app.js:367-374,437,413-415` — Ausgabeflächen beendeter Tabs bleiben als versteckte DOM-Knoten liegen
  - Evidence: Beim Tab-Entzug (Zeile 437) bzw. `reset()` wird nur der Tab-Button entfernt; das zugehörige `pre.outpane` (inkl. `dataset.text` mit kompletter Subagent-Ausgabe) bleibt im Logcard hängen — über lange Läufe mit vielen Subagenten sammeln sich versteckte Panes mit vollem Ausgabetext. Daten-Nachladen ist dadurch zwar korrekt verhindert, Speicherpflaster gedeckelt, aber die Karte verwässert.
  - Required fix: Beim Tab-Entzug die zugehörige Pane aus Karte und `panes`-Map entfernen bzw. Test-Agent bitten, einen langen Mehr-Subagent-Lauf gegen ein Wachstums-DOM zu prüfen.

- [Minor] `bin/web/app.js:429-430` — dokumentierte „dauerhafte" manuelle Tabwahl wird bei jeder Kompositionsänderung zurückgesetzt
  - Evidence: `fresh=next!==order; if(fresh)manual=false;` — startet während der laufenden parallelen Lage ein weiterer Subagent, wechselt die Ansicht doch wieder automatisch; das dokumentierte Verhalten „der erste eigene Tab-Klick schaltet die automatische Auswahl dauerhaft ab" (`docs/features/F24.md:46-47`) ist so nicht eingehalten. Verhaltensrelevante Doku-Differenz, nicht direkt kritisch.
  - Required fix: Semantik klären (Auto-Follow nur für brandneue Subagenten vs. Kompositionswechsel) und Doku/Code anpassen oder Abstand als Grenze dokumentieren.

- [Minor] `tests/browser/test_f24_output_tabs_ui.py:307-339` — Aktualisierungszeitpunkt im Ende-Testfall hängt an einem festen Fenster
  - Evidence: Nach dem Registerwechsel wird mit `time.sleep(1.2)` plus `visible_text(AGENT, timeout=2)` gegen die 3-s-Pollperiode gewartet; liegt der letzte Poll knapp vor dem Registerwechsel, läuft die Assertion in ein knappes Fenster. Korrekte Aussage, aber zeitkritisch.
  - Required fix: Testfall robust machen, indem direkt der Poll-abhängige Stand über einen Run-Status-abhängigen Poll abgewartet wird; dies kann beim Test-Agenten angefordert werden.

## Verification
- Change set reviewed: Ausgangscommit `5f13220` → Arbeitsbaum auf Branch `vibe/vibe-F24-1794139598747889668-2696346-28951` (Commit folgt nach eigenen Angaben erst nach Review).
- Git commands run by me: keine — Shellzugriff im Review-Kontext verweigert (`Permission denied: shell` für `git status`/`git log`). Diff-/Soll-Abgleich basiert auf dem übergebenen `-U20`-Diff, ergänzt durch statisches Review über den Arbeitsbaum, abgestimmt gegen Originalquellen; Originaldateien am Ausgangscommit (`git show 5f13220:<pfad>`) konnte ich nicht gesondert ziehen, der gelieferte Unified-Diff deckt die gesamten Änderungen einschließlich Kontext ab.
- Checks with supplied output: `unittest` F24 (5/5 OK), Playwright F24 (4/4 OK), `node --check`, `check-import-manifest.py` (56 Dateien), `verify.sh quick` (Exit 0), Unit-/Browser-Vergleichsbaseline aus dem F24-Report (identische Vorab-Fails an Ausgangsstand und F24-Stand). Alles nur berichtete Ausführungsergebnisse des Coding-/Test-Agenten; ich habe keine einzige Prüfung selbst ausgeführt.
- Checks not independently run: alle Build-/Unit-/Browser-Prüfungen; rote Phase; Testprovenienz des Test-Agenten (laut AGENTS.md abnahmerelevant — durch den übergebenen Branch ohne geforderten Commit in dieser Arbeitskopie nicht beweisbar, hier als verbleibendes Risiko vermerkt).
- Important areas inspected: `bin/vibe-web.py` (Endpoint `/api/subagents`, `run_is_active`, `subagents_of`, `live_subagents`), `bin/web/app.js` (logView/agentTabs/subagentCard/detail-Verkabelung), `bin/web/styles.css`, `bin/vibe_runs.py` (`LIVE_STATES`, `latest`, CLI), beide F24-Testdateien, `docs/features/F24.md`, `docs/baseline.md`, Manifest-Diff, F13-Browsertests (Tablisten-Eindeutigkeit ganzseitig `test_project_detail_ui.py:163-164` — lazy-mount vermeidet die Kollision korrekt außerhalb von Läufen mit parallelen Agenten; berichtete Testläufe zeigen dort 1 Fail, aber exakt denselben am Ausgangsstand).
- Remaining risks: (1) Das Medium (Tastaturbedienung) — nach dem Fix erfordert es eine fokussierte Testabdeckung durch den Test-Agenten; (2) Trilium-Synchronisation ist im Bericht des Coding-Agenten nicht belegt — steht laut AGENTS.md als Pflichtdokumentation zusätzlich zur lokalen `docs/features/F24.md` und ist für den Abschluss nachzuholen; (3) Reviewrunden-Ablage `docs/reviews/F24-review-<runde>.md` folgt erst nach Überantwortung dieser Antwort; (4) Die verbindliche `verify.sh full`-Vollprüfung läuft laut Bericht nur auf der tmpfs-Kopie /dev/shm (NTFS-Begrenzung aus B5 dokumentiert) — übliche Maßnahme, bleibt aber ein übernommenes, nicht aus eigener Prüfaufsicht stammendes Verfahren.

Fazit: Die fünf Akzeptanzkriterien des Tickets sind funktional durch echte, keineswegs assertschwache Tests an Produktionskomponenten abgedeckt, der Backendkontrakt (LIVE-Register als einzige Quelle des Agentennamens, Fehlen des Felds ohne Lauf) ist sauber, sicher (Tokenpflicht unangetastet, nur der Agentenname als Feld, DOM-Text nie als HTML), KISS-nah und ohne bewusste unnötige Komplexität. Der einzige Blockierungsbaustein ist der fehlerhafte Tastatur-Handler, der als dokumentierte Funktionsweise des neuen Tabs elementar verletzt und zugleich zeigt, dass die frisch implementierte Zugänglichkeit nicht getestet wurde. Nach dem Fix und entsprechender, durch den Test-Agenten geschriebener Tastatur-Abdeckung ist bei der Wiederholungsreview PASS möglich.
