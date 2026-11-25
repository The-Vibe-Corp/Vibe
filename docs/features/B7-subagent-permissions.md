# B7 — Subagenten-Rechte beim Vorlagen-Rendering

Status: Implementiert (2026-11-23)
Ticket: FEEDBACK.md „Generation of agent file subagent permissions does not work correctly for new opencode v2“ (Art: Bug)
Branch: `feature/korbat/b7`
Ausgangscommit: `8931f7b`

Hinweis zum Ablageort: Der Pfad `docs/features/B7.md` gehört dem älteren
B7-Nummernkreis „GitHub-Authentifizierung“ und bleibt unangetastet; diese
Dokumentation liegt deshalb unter dem eindeutigen Namen
`B7-subagent-permissions.md` (analog B6 mit `B6-statusmarken.md`).

## Ziel

Beim Regenerieren einer Agentendatei über die GUI-Rechte-Vorlage (klassische
UI) darf die Subagenten-Policy der Eingabedatei nicht stillschweigend auf
„keine“ zurückgesetzt werden. Rechte-Vorlage und Subagenten-Rechte sind zwei
unabhängige Dimensionen im selben `permissions:`-Block: Nur die
Nicht-subagent-Regeln kommen aus der Vorlage, die Subagenten-Regeln geben die
Policy der Eingabedatei wieder.

## Beobachtetes Fehlverhalten

Nach der v2-Regenerierung über die GUI-Rechte-Vorlage stand in der Datei
immer `subagent * deny`, obwohl die Oberfläche die Subagenten-Auswahl
(z. B. „alle“) anzeigte. Der Orchestrator konnte deshalb keine Subagenten
rufen; der Nutzer musste die Datei manuell auf allow reparieren.

## Ursache

`agent_render_fields` in `bin/vibe` ersetzt beim nichtleeren
`values.permission` über `_apply_agent_fields` den gesamten Rechteblock durch
die Vorlage; jede Vorlage (`PERMS`) enthält als Standard `("subagent", "*",
"deny")`. Die klassische UI sendet die Subagenten-Auswahl
(`task_allowed`/`task_all`) nur, wenn sie sich gegenüber dem Ladezustand
geändert hat (`app.js`, `taskChanged`). Beim Regenerieren einer v1-Datei
(`task: allow` → Anzeige „alle“) mit Preset wird daher keine Auswahl gesendet,
und die subagent-Regeln werden stillschweigend auf deny zurückgesetzt.

## Umsetzung

Kleinste Änderung ausschließlich in `bin/vibe`:

- `agent_render_fields` erfasst beim Anwenden einer Rechte-Vorlage vor dem
  Ersetzen die Subagenten-Policy der **Eingabedatei** über
  `agent_task_policy(text)` (versteht v2-Regeln und den v1-task-Fallback).
- Nach `_apply_agent_fields` stellt die neue Hilfsfunktion
  `_subagent_policy_to_v2` die Subagenten-Regeln des (nun immer v2-förmigen)
  `permissions:`-Blocks über
  `_subagent_rules(policy["allowed"], allow_all=policy["mode"] == "all")`
  wieder her.
- Liegt keine Freigabe vor (Policy `none`: v2-Block ohne subagent-Regeln,
  v1 ohne `task`, kein Block), bleibt der Vorlagen-Standard
  `subagent * deny` unangetastet — damit der Block weiterhin als reine
  Vorlage erkennbar ist (`agent_fields(...)["permission"]`).
- Keine Änderung an `_apply_agent_fields`, `agent_render_task`,
  `agent_template`, `bin/vibe-web.py`, `app.js` oder den Vorlagen. Die
  Serverreihenfolge „erst Felder, dann Auswahl“ in `vibe-web.py` bleibt
  wirksam: eine ausdrücklich gesendete Auswahl gewinnt weiterhin.

## Entscheidungen

- **Policy-Erhalt als zentrale Serversemantik.** Die Korrektur liegt im
  gemeinsamen Render-/Apply-Pfad `agent_render_fields`, den sowohl „Speichern“
  als auch „In Rohtext übernehmen“ durchlaufen; damit ist sie end-to-end über
  die Web-API wirksam, ohne UI-Logik zu verändern.
- **Keine Änderung an den Vorlagen.** Der Vorlagen-Standard
  `subagent * deny` für die Neuanlage bleibt unverändert; nur die Policy der
  Eingabedatei wird beim Regenerieren erhalten.
- **Kosmetische Folge (bewusst, kein Handlungsbedarf).** Ein Block aus
  Vorlagen-Rechten plus erhaltenen Subagenten-Freigaben entspricht keiner
  reinen Vorlage mehr; `agent_fields(...)["permission"]` zeigt dann leer
  („individuell“), während die Subagenten-Auswahl „alle“ zeigt. Das ist
  ehrlich und in den Tests nicht erzwungen.
- **Keine neuen Fehlerwege.** `agent_task_policy` kann bei unlesbarem
  Frontmatter `ValueError` werfen; das entspricht dem bestehenden Verhalten
  von `agent_render_fields` über `_frontmatter_parts`.

## Verifikation

Ausgeführte Befehle (Arbeitskopie
`/var/log/custom/vibe-dev/worktrees/vibe-B7-Owlqs4`, Ausgangscommit
`8931f7b`):

- `python3 -m unittest tests.unit.test_agent_management -v`
  → Ran 21 tests, OK.
- `python3 -m unittest tests.unit.test_agent_management tests.unit.test_agent_management tests.unit.test_agent_management -v`
  → Ran 124 tests, OK.
- `python3 -m unittest tests.unit.test_agent_management tests.unit.test_project_agents tests.unit.test_project_agents`
  → Ran 70 tests, OK.
- `python3 scripts/check-import-manifest.py` → OK.
- `bash scripts/verify.sh quick` → Exit 0.
- `bash scripts/verify.sh package` → Exit 0.
- `bash scripts/verify.sh full --jobs 4` (einmal vor der Abnahme) →
  `VERIFY_RESULT: mode=full tests=2620 failed_modules=16`, Exit 7. Das
  neue Modul `tests.unit.test_b7_subagent_permissions` ist im Volllauf
  grün. Alle 16 fehlgeschlagenen Module sind Vorbestände der
  Umgebung/Transportnotizen, nicht B7-Regressionen:
  - 9 Module am Ausgangsstand `8931f7b` (git-archive-Export,
    venv-Interpreter, bereinigte Umgebung) identisch rot reproduziert:
    `test_ap7_korbat_rules` (transportierte AGENTS.md-Divergenz, dieselbe
    fehlschlagende Prüfung), `test_ap8_github_checkout`,
    `test_b16_runner_wiring`, `test_b17_isolation`,
    `test_b4_install_empty_runs`, `test_install_lifecycle`,
    `test_project_management` (Template-/AGENTS.md-Familie, F22/AP10
    §4.2), `test_rebuild_profile`, `test_release`,
    `test_setup_vibe`.
  - `test_ap12_github_readiness`: Hygiene-Treiber sind
    `/home/vibe/...`-Pfade in `tests/browser/test_f33_*.py` — nachweislich
    seit Commit 831ecd1 (F33) im Ausgangsstand enthalten; die
    B7-Dateien sind unversioniert und nicht Gegenstand der
    versionierten Inhaltsprüfung. Zweiter Fehler betrifft den lokalen
    Test-Agent-Bestand (Laufzeitumgebung).
  - 6 Module (u. a. `test_sandbox`, `test_b5_sandbox`,
    `test_b13_private_server_runner`, `test_b4_pi_agent_dir`,
    `test_project_guide`) sind die dokumentierte
    bwrap/SANDBOX-Umgebungsfamilie (AP9/AP10/AP6): bei direktem Aufruf
    grün bzw. geskippt, rot nur unter der isolierten
    Prüfumgebung — ohne Bezug zur Agentendarstellung.
  - Exit 7 folgt der bewusst leer ausgelieferten committeten Baseline
    (`tests/verify-baseline.json`, `envs={}`) ohne `VERIFY_ENV`
    (dokumentierter Nutzerzustand aus AP7); kein Exit 6, da 2620 ≥ 2000.

Unabhängiger Test-Bericht (Rotphase belegt): siehe
`docs/reviews/B7-subagent-permissions-test-agent-report.md` (21 Testfälle,
davon 8 in der Rotphase rot). Unabhängiges Review:
`docs/reviews/B7-review-3.md`, `Verdict: PASS` (0 Befunde).

## Grenzen

- **Nur globaler Scope per API.** Subagenten-Rechte lassen sich über die API
  nur für systemweite Agenten setzen (`scope != global` wird abgelehnt); die
  UI erzwingt `global`. Ob `agent_render_fields` für Projektagenten mit
  v1-`task`-Einträgen dieselbe Erhaltungsregel anwenden soll, ist nicht
  getestet (die Funktion verhält sich für jeden Scope gleich, da der
  Policy-Erhalt scope-unabhängig ist).
- **Kein JS-/Browserlauf.** Der Browser-Klickpfad (`taskChanged`) wurde nicht
  ausgeführt; die Payload-Sequenzen sind serverseitig nachgestellt.
- **Trilium nicht verfügbar.** Es ist keine Trilium-MCP-Verbindung
  konfiguriert; die Dokumentation liegt ausschließlich als
  Repository-Datei vor.
- **Kosmetische Folge (siehe Entscheidungen).** Ein regenerierter Block mit
  erhaltenen Subagenten-Freigaben wird als „individuell“ angezeigt.
