# Review AP22 — Gesamtabnahme (Runde 2 / Review-Fix-Runde)

- **Arbeitspaket:** AP22 „New vibe ui“ (`docs/features/AP22.md`, `TICKETS.md`): Neuaufbau der Weboberfläche für nicht-/semi-technische Nutzer; klassische UI bleibt als Option erhalten (standardmäßig aus); CLI-Parität als Qualitätskriterium.
- **Paketbranch:** `feature/m0p/ap22`; unter Review: Commits `4a5eeed..cf76ab3` (HEAD `cf76ab3`), Fix-Runde `6dc547b..cf76ab3`, Basis `f49940d`.
- **Rolle:** unabhängiger Review-Agent (code-reviewer, Modell `opencode/hy4-flash-free` aus der Projektkonfiguration `.vibe/agents.json`); keine Implementierung, keine Änderung an Produktionsdateien. Offenlegung: die Reviewer-Session hatte kein Datei-Schreibwerkzeug; der Koordinator hat diese Datei mit dem wörtlichen Reviewer-Bericht angelegt — jede Bewertung und jedes Urteil stammt vom Review-Agenten.
- **Datum:** 2026-11-20
- **Round-1-Referenz:** `docs/reviews/AP22-review-1.md` — „Verdict: CHANGES REQUIRED“, 5 Medium + 2 Minor. Diese Datei prüft ausschließlich, ob genau diese Befunde behoben und belegt sind.
- **Vision-Bestätigung:** Die Fix-Runde bleibt der in `docs/features/AP22.md` („Ziel und Zielgruppe“, „Feste Entscheidungen“) verbindlich festgeschriebenen Vision treu: neue UI für die Hauptzielgruppe, `/classic` als dauerhaft erreichbare Option, CLI-Parität über bestehende `/api`-Endpunkte ohne Änderung des Backend-Verhaltens. `git diff c3364fe..cf76ab3 -- bin/vibe-web.py bin/web/app.js bin/web/styles.css` ist leer; die Paritätslücken wurden in der neuen UI geschlossen, nicht im Bestand.
- **Prüfmethode:** Code-Lesen der committeten Blobs per `git show cf76ab3:<path>`. Der Arbeitsbaum enthält laufende kosmetische Änderungen eines anderen Agenten (`nova-activity.js`, `nova.css`) und wurde für keine Bewertung verwendet. Grünlauf-Meldungen sind vom Koordinator gelieferter FremdNachweis; der Reviewer hat keine Build-, Test- oder Verify-Läufe selbst ausgeführt.

## Summary

- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- **Verdict: PASS**

Alle fünf Medium-Befunde und der Minor-Befund 7 sind in `cf76ab3` umgesetzt und durch die drei neuen Testsuiten samt dokumentierter Rotphase belegt. Der Minor-Befund 6 (Validierungsabschnitt in `AP22.md`) ist ausdrücklich als Koordinator-Abschlussarbeit zum Final-Commit vorgesehen und nicht blockierend. Es wurden keine neuen Findings festgestellt.

## Befunde und Belege (Runde 1 → Runde 2)

| Befund (Runde 1) | Fix-Beleg im Commit `cf76ab3` | Testbeleg | Status |
| --- | --- | --- | --- |
| 1 [Medium] Git-&-GitHub-Parität fehlte; `enabled: !!github.enabled` verhinderte Aktivierung | `bin/web/nova-project.js:517` `nvpGithubSection()`: Aktivierung + Einstellungen (`:552`, Payload `{action:'settings', enabled: enabled.checked, …}` statt hartcodiertem Wert), Token speichern/entfernen (`:578`, `:589`) mit maskierter Statuszeile `[data-nv-github-auth]` (`:574`), Verbindungsergebnis `[data-nv-github-connection][data-nv-ok]`, Branches + Checkout (`:621`), Pull (`:632`), Push mit Quelle/Ziel (`:637`–`:642`), Issues + Label-Import (`:654`, `:672`), Zwei-Schritt-Merge-Request mit `[data-nv-github-pr-confirm]` (`:680`–`:682`). Stichprobe gegen Klassik (`app.js:1013`, `:1020`, `:1051`): `token.save`, `settings` und `pr` payload-identisch (Name wird zentral via `post()` ergänzt). | `tests/browser/test_ap22_project_ui.py:1025–1300` `GithubParityTest` (10 Fälle) — vom Koordinator grün gemeldet (10/10); Rotphase mit Verbatim-Auszug in `docs/reviews/AP22-test-agent-report-mc.md`, Abschnitt „Review-Fix-Runde — Rotphase“ (12 Failures/9 Errors am Stand `6dc547b`). | PASS |
| 2 [Medium] Glocke ignorierte blockierte Pakete + fehlgeschlagene Läufe | `bin/web/nova-core.js:432` `NV.pulse()` liefert `questions`, `running`, `failed` (`run.state === 'failed'`) und `blocked` (Pakete mit `BLOCKIERT` aus `/api/project`); `refreshBell()` (`:461`) summiert alle vier Quellen im Badge (`:464`) und verlinkt Fragen → Projekt, Blockiert → `/work` (`:482`), Failed → `/output` (`:488`), Running → `/output`. | `tests/browser/test_ap22_activity_ui.py:774` `test_bell_counts_questions_blocked_and_failed_with_links` — grün gemeldet (3/3 der `ReviewActivityParityTest`); Rotphase: „Die Glocke zählt nicht die erwarteten Quellen (erwartet 3, gesehen 1)“. | PASS |
| 3 [Medium] Laufzeile ohne Stop | `bin/web/nova-activity.js`, `NV.views.activity()` → `p.running.forEach`: Zeile `[data-nv-run="<projekt>"]` mit Öffnen-Link und `stop-run`-Knopf, `window.confirm(...)` und `api('/api/stop', {name: name})`, danach `NV.render()` (Zeilennummern im Commit nicht verifiziert — Working-Tree-Kosmetik; Inhalt aus `git show cf76ab3:…` gelesen). | `tests/browser/test_ap22_activity_ui.py:846` `test_run_row_offers_stop_and_stops_the_run` — grün gemeldet; Rotphase: „Die Laufzeile [data-nv-run] fehlt“. | PASS |
| 4 [Medium] Zusammenfassungs-Kacheln fehlten | `bin/web/nova-activity.js`, `NV.pulse().then(...)`: `[data-nv-activity-tiles]` mit `data-nv-tile="running|questions|blocked"` und echten Zahlen (Zeilennummern wie bei 3 nicht verifiziert; Inhalt aus dem Commitblob gelesen). | `tests/browser/test_ap22_activity_ui.py:830` `test_activity_summary_tiles_show_running_questions_and_blocked` — grün gemeldet; Rotphase: „Die Zusammenfassungs-Kachel 'running' fehlt“ (ebenso questions/blocked). | PASS |
| 5 [Medium] Editor bearbeitete fest `scope=global`, Projektagenten ins Leere/falsche Datei | `bin/web/nova-agents.js:19` `nvAgentRoute()` parst `#/agents/<scope>/<name>` (Rückwärtskompatibilität für `#/agents/<name>` erhalten); `nvAgentEditor(name, scope, …)` (`:343`) lädt `GET /api/agent?scope=…&name=…` und sendet `scope` bei Save (`:454`), Backup (`:508`), Restore (`:526`), Copy (`:545`) und Delete (`:560`); Karten tragen `[data-nv-agent-scope]` + Badge (`:125`, `:128`). Ein projektbezogener Save kann damit nicht die globale Datei treffen. | `tests/browser/test_ap22_agents_ui.py:1034–1200` `ProjectScopeTest` (4 Fälle) — grün gemeldet (4/4), u. a. `test_save_project_agent_keeps_global_file_unchanged` (`:1133`); Rotphase: 3 Failures/1 Error am Stand `6dc547b`. | PASS |
| 6 [Minor] Validierungsabschnitt `docs/features/AP22.md` ist Platzhalter | Im Commit `cf76ab3` weiterhin Platzhalter. Vom Koordinator ausdrücklich als Final-Commit-Arbeit eingeplant; nicht durch den Coding-Agenten der Fix-Runde zu leisten. | Kein Test erforderlich (Dokumentation); Koordinator-Notiz „scheduled, not blocking“. | SCHEDULED (nicht blockierend) |
| 7 [Minor] Agentenkarte ohne Löschknopf | `bin/web/nova-agents.js:116–133`: Karte mit `agent-delete`-Knopf und sichtbarer Inline-Bestätigung (`[data-nv-confirm]`), `api('/api/agent', {action:'delete', scope, name})` — scope-genau auch auf der Karte. | `tests/browser/test_ap22_agents_ui.py:1167` `test_card_delete_removes_project_agent_but_keeps_global` — grün gemeldet; zusätzlich `test_delete_removes_the_agent_file` (`:951`). | PASS |

## Regressionssicherheit

- `git diff 6dc547b..cf76ab3 --stat`: genau 10 Dateien — `bin/web/i18n.js`, die vier nova-Dateien (`core`, `project`, `activity`, `agents`), `docs/import-manifest.json`, `docs/reviews/AP22-test-agent-report-mc.md` sowie die drei Browsertestsuiten (`test_ap22_project_ui.py`, `test_ap22_agents_ui.py`, `test_ap22_activity_ui.py`). Kein unerwarteter Produktions- oder Testdatei-Handle.
- `git diff c3364fe..cf76ab3 -- bin/vibe-web.py bin/web/app.js bin/web/styles.css`: leer — Routing und klassische UI unverändert.
- `innerHTML`: in den nova-Dateien nicht vorhanden; die einzigen Treffer in `bin/web/` sind erläuternde Kommentare („nie als innerHTML“, „kein innerHTML“) in `nova-core.js:50`, `nova-activity.js:7`, `nova-output.js:13/136`, `app.js:692/877`. DOM-only-Knotenbau bleibt gewahrt.
- i18n: die neuen Schlüssel wurden in **beide** Wörterbücher aufgenommen (`bin/web/i18n.js`, u. a. `Basis-Branch (optional)`, `Token speichern`, `Lauf fehlgeschlagen`, `Laufend`, `Offene Fragen`, `Lauf wirklich stoppen?`, `Global`, `Löschen fehlgeschlagen.`). Vom Koordinator gemeldet: 999/999 Schlüssel, 0 Duplikate.
- Grün-/Baseline-Meldungen des Koordinators (FremdNachweis): 9 AP22-Suiten grün auf `cf76ab3`; `GithubParityTest` 10/10, `ReviewActivityParityTest` 3/3, `ProjectScopeTest` 4/4; Unit-Routen 21/21; i18n/questions 85 OK; verify quick Exit 0; Full-Verify auf dem committeten Baum: statische Checks grün, Unit-Discovery nur die vorbestehenden Baseline-Failures (138 Namen, identisch auf `f49940d` reproduziert) plus 6 tmux-Familienfälle, die nur in der Verify-Staging-Umgebung scheitern und in einfachen Läufen am selben HEAD bestehen (dokumentierte Umgebungsgrenze).

## Umstände

Wie in `AP22-review-1.md` offengelegt, scheiterten vier vorherige Review-Anläufe an Provider-Nutzungslimits bzw. am Schrittlimit, bevor eine Review-Datei entstehen konnte; der Koordinator legte die Runde-1-Datei mit dem wörtlichen Bericht des Review-Agenten an. Runde 2 (auf dem vorab konfigurierten Modell `opencode/hy4-flash-free`) prüft den behobenen Zustand `cf76ab3` mit derselben Methodik: Code-Lesen der committeten Blobs plus vom Koordinator gelieferte Testnachweise. Ausdrücklich nicht selbst ausgeführt wurden alle Build-, Test- und Verify-Läufe; die Bewertung der Grünläufe ist FremdNachweis. Während dieser Runde arbeitete ein anderer Agent an kosmetischen Polituren im Working Tree; um deren nicht-fachliche Änderungen auszuschließen, wurden sämtliche Befundbelege aus `git show cf76ab3:<path>` gelesen.

## Bekannte, nicht blockierende kosmetische Reste

Rein gestalterische Punkte aus der visuellen Bestätigung: H1-Abstände, Badge-Baseline und eine Session-Beschriftung. Eine abschließende Kosmetik-Runde war während dieser Review in Arbeit; diese Punkte berühren weder die Commit-Inhalte von `cf76ab3` noch einen der sieben Befunde.

## Verification

- Change set reviewed: `6dc547b..cf76ab3` (unter Review `4a5eeed..cf76ab3`), ergänzt um `AP22-review-1.md`, `AP22.md`, den Testbericht `AP22-test-agent-report-mc.md` und die Payload-Referenz `bin/web/app.js`.
- Git commands run by the reviewer: `git status --short`; `git show cf76ab3:bin/web/{nova-project,nova-core,nova-activity,nova-agents}.js`; `git show cf76ab3:docs/features/AP22.md`; `git show cf76ab3:docs/reviews/AP22-test-agent-report-mc.md`; `git diff 6dc547b..cf76ab3 --stat`; `git diff 6dc547b..cf76ab3 -- bin/web/i18n.js`; `git diff c3364fe..cf76ab3 -- bin/vibe-web.py bin/web/app.js bin/web/styles.css` (leer).
- Checks with supplied output: alle im Abschnitt „Regressionssicherheit“ genannten Grünläufe und Rotphase-Auszüge — vom Koordinator bzw. aus dem committeten Testbericht geliefert.
- Checks not independently run: sämtliche Build-, Lint-, Unit-, Browser-, i18n- und Verify-Läufe.
- Remaining risks: der Validierungsabschnitt in `AP22.md` wird erst im Final-Commit gefüllt (scheduled); die sechs tmux-Familienfälle sind eine dokumentierte Verify-Umgebungsgrenze; die klassische UI bietet zusätzliche GitHub-Aktionen (`link`/`unlink`/`fetch`), die weder Runde-1-Befund noch Fix-Auftrag umfassten und daher hier nicht bewertet wurden.

Verdict: PASS
