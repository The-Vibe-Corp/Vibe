# AP2-Korbat — opencode-v2-Berechtigungssyntax und die Subagenten general/explore

Stand: 2026-11-21
Ticket: TICKETS.md AP2-Korbat („Change permission syntax in agent markdowns to opencode v2 and expose general and explore agents in GUI“)
Arbeitsbranch: `feature/korbat/ap2-korbat-2`
Basiscommit: `95b3790`

## Ziel

1. Generierte Agenten-Markdowns nutzen die opencode-v2-Berechtigungssyntax
   (`permissions:`-Regelliste mit `action`/`resource`/`effect`, `shell` statt
   `bash`, `subagent` statt `task`).
2. Die opencode-eigenen Subagenten `general` und `explore` sind in der
   Projekt-Agentenauswahl als „OpenCode“ sichtbar, umschaltbar und mit einem
   eigenen Modell belegbar — projektbezogen, ohne eigene Dateien/Prompts/
   vibe-Metadaten. Erlaubt/verboten wird ausschließlich über die
   opencode-Subagenten-Mechanik (je Projekt `disabled`/`model` in der
   Inline-Konfiguration des Läufers).

## Umsetzung (Datei für Datei)

- `bin/vibe`
  - `PERMS` ist jetzt eine v2-Regelliste (action/resource/effect); die
    Vorlagen `voll`, `lesen`, `lesen_git` decken die Vorgaben des Tickets ab.
    `V1_PERMS` bleibt nur zur Migration bestehender v1-Dateien erhalten.
    `permission_block`/`edit_permission_lines` erzeugen v2-Zeilen (edit:
    breite Deny-Regel zuerst, danach je Verzeichnis allow — „letzte passende
    Regel gewinnt“).
  - `_v2_rules` liest einen `permissions:`-Block zeilenorientiert; `_parse_agent_text`
    erkennt neben `permission` (v1) jetzt auch `permissions` (v2).
  - `agent_fields` vergleicht v2-Blöcke gegen die Vorlagen; ein v1-Block gilt
    als individuell. `_apply_agent_fields`/`agent_render_fields` ersetzen einen
    v1- ODER v2-Block durch den v2-Block und lehnen Inline-Formen beider
    Schlüssel ab.
  - `agent_task_policy` wertet v2-`subagent`-Regeln aus (letzte Regel gewinnt,
    Stern-Regel setzt gesammelte Namen zurück); ohne v2-Block bleibt der
    v1-`task`-Fallback. `agent_render_task` schreibt nur die Subagenten-Regeln,
    migriert einen vorlagenkonformen v1-Block komplett auf v2 und lässt einen
    individuellen v1-Block in v1-Syntax.
  - `_edit_grants_write`/`_rewrite_edit_block` sind v2-fähig (edit-Regeln
    gezielt ersetzen/erkennen; kein edit-Eintrag = Schreiben erlaubt); ohne
    jeden Block wird ein v2-Block angelegt; v1-Bestandsblöcke bleiben
    funktionsfähig.
  - Projekt-Agentenauswahl Version 3: `PROJECT_AGENTS_KEYS` um `opencode`
    ergänzt, `OPENCODE_AGENTS = ("general", "explore")`. `_project_agents_check`
    validiert den Abschnitt (nur general/explore, `aktiv` als JSON-Bool,
    `modell` leer oder gültiges Muster; Startliste lehnt general/explore ab).
    `_project_agents_read` migriert Version 1 und 2 auf Version 3 mit
    opencode-Defaults.
  - `project_agent_rows` liefert zusätzliche Zeilen für general/explore
    (`opencode=True`, `configured/selected` aus `aktiv`, `effective_model`
    aus `modell`, leer = geerbt); `project_agent_inventory` bleibt
    Datei-Agenten. `project_agent_set` schreibt für general/explore nur den
    opencode-Abschnitt (ungültige Werte: `ValueError` ohne Schreiben).
    `cmd_project_agents` zeigt die opencode-Zeilen (Zustand + Modell).
  - `_remap_project_agents` erhält den opencode-Abschnitt.

- `bin/vibe-run.sh` (B1-Block, Python-Heredoc)
  - Liest zusätzlich den `opencode`-Abschnitt (nur `$P/.vibe/agents.json`).
    `aktiv=true` + Modell → Modell wie `modelle` in beide Maps (`agent` und
    `agents`); `aktiv=false` → `agents.<name>.disabled=true` (nie in der
    Legacy-`agent`-Map, Modell wird nicht angewandt). Früher Exit 0 nur ohne
    wirksame Projektmodelle und ohne Deaktivierungen; sonst wird
    `OPENCODE_CONFIG_CONTENT` gesetzt (bestehender JSONC-Inhalt semantisch
    gemergt) und die Serverwahl bleibt wie B1.

- `bin/vibe-web.py`/`bin/vibe_services.py`
  - GET `/api/project-agents` reicht die opencode-Zeilen über
    `project_agent_rows` durch; POST `/api/project-agents` leitet
    `agent`/`selected`/`model` an `project_agent_set` weiter (400 bei
    ungültigen Werten). `/api/agent` und `/api/agent_template` bleiben
    unverändert (die Feldübergabe `permission` bleibt).

- `bin/web/app.js`, `bin/web/nova-project.js`, `bin/web/i18n.js`
  - `projectAgentsCard` und `nvpTeamSection` kennzeichnen general/explore
    sichtbar als „OpenCode“ (Attribut `data-opencode` bzw. Text), bieten den
    bestehenden Toggle (selected) und die Modell-Auswahl (override) an und
    erklären, dass Abwahl das Aufrufen durch andere Agenten in Läufen dieses
    Projekts sperrt. Neue UI-Texte sind im en- und de-Wörterbuch aufgenommen.

- `templates/common/opencode.json`
  - Auf v2 umgestellt: `permissions`-Liste mit `edit`/`shell` allow.

- `docs/import-manifest.json`
  - SHA-256/Größe der geänderten in-scope-Dateien aktualisiert und
    `aenderungen`-Eintrag „AP2-Korbat“ ergänzt.

## Tests und Nachweise

Alle Läufe mit bereinigter Umgebung (`env -u VIBE -u VIBE_INSTALL … -u SANDBOX …`),
temporärem HOME und opencode-Attrappe; keine Modellaufrufe.

- Unabhängiger Test-Agent (Rotphase vor der Implementierung, Bericht
  `docs/reviews/AP2-Korbat-test-agent-report.md`): 64 Fälle neu in
  `tests/unit/test_ap2_opencode_agents.py`; Rotphase am Ausgangsstand
  38 Failures + 6 Errors. Zwei Test-Setup-Defekte wurden nach Verifikation
  vom Test-Agenten korrigiert (Berichtsnachträge 10 und 10.1); beide
  korrigierten Fälle sind danach grün.
- `python3 -m unittest tests.unit.test_ap2_opencode_agents -v`
  → `Ran 64 tests … OK` (Exit 0).
- `python3 -m unittest tests.unit.test_project_write_dirs -v`
  → `Ran 40 tests … OK` (Exit 0; belegt im Test-Agenten-Bericht, Nachtrag 10.1).
- Fokusmodule gesamt (`test_ap2_opencode_agents`, `test_agent_management`,
  `test_ap03_agent_management`, `test_project_write_dirs`, `test_project_agents`,
  `test_b1_project_agent_models`, `test_f32_subagent_self_spawn`)
  → `Ran 235 tests`, `FAILED (failures=1, errors=6)`: ausschließlich die 7
  vorbestehenden `ensure_test_agent`-Baseline-Fehler
  (`test_project_agents.RunSelectionTest` 1 Error + 1 Failure,
  `test_ap03_agent_management.VibeRunGateTest` 5 Errors), identisch am
  Ausgangscommit `95b3790` reproduziert. Alle AP2-Fälle sind grün; B1
  (`test_b1_project_agent_models`) und F32 (`test_f32_subagent_self_spawn`)
  bleiben vollständig grün.
- `bash -n bin/vibe-run.sh` → Exit 0; `python3 -m py_compile bin/vibe
  bin/vibe-web.py bin/vibe_services.py` → Exit 0;
  `python3 scripts/check-syntax.py` → OK (207 Python-, 8 Bash-, 3 JSON-Dateien);
  `python3 scripts/check-import-manifest.py` → OK (67 Dateien).
- `bash scripts/verify.sh quick` → Exit 0.
- `bash scripts/verify.sh package` → Prüf-Exit 5, ausschließlich durch dieselben
  7 vorbestehenden Baseline-Fehler im Prüflog belegt (`Ran 235 tests`,
  `failures=1, errors=6`, alle `ensure_test_agent`-Klasse).
- Browser-Testfälle (klassisch `test_project_agents_ui.py`, Nova
  `test_ap22_project_ui.py`, außerdem angepasst `test_ap03_agents_ui.py`,
  `test_write_dirs_ui.py`) sind geschrieben und syntaxgeprüft (`py_compile`,
  Exit 0); eine Ausführung mit echtem Browser war in dieser Umgebung nicht
  möglich (Python-Modul `playwright` nicht installiert) — ehrlich als Grenze,
  kein Verhaltensnachweis.

### Vollprüfung und Baseline-Vergleich

`bash scripts/verify.sh full` (einmalige Abnahmeprüfung, bereinigte Umgebung):
`Ran 2178 tests in 1016.094s`, `FAILED (failures=56, errors=100, skipped=15)`,
Prüf-Exit 5.

Baseline am Ausgangscommit `95b3790` (identische Umgebung, Kopie ohne
AP2-Änderungen): `Ran 2114 tests`, `FAILED (failures=54, errors=113,
skipped=15)`. Die 64 zusätzlichen Tests sind die neuen AP2-Fälle; sie sind
im Volllauf vollständig grün (2114 + 64 = 2178).

Fallbezogener Abgleich der misserfolgten Fälle (Basis: Prüf- und
Baselinelauf, Bereinigung um Subtest-Parameter):

- **Neue misserfolgte Fälle gegenüber der Baseline: keine** (leere
  Differenzmenge).
- 11 Fallfamilien der Baseline bestehen jetzt (u. a. mehrere
  `test_ap12_github_readiness`-Umgebungsfälle und
  `test_project_management.TemplateRulesTest`-Fälle; letztere sind auf die
  lokal vorhandene, nicht versionierte `FEEDBACK.md`/Arbeitsbaum-Situation
  zurückzuführen, nicht auf AP2-Code).
- Alle verbleibenden 148 misserfolgten Fallfamilien sind identisch mit der
  Baseline: dokumentierte Umgebungsgrenzen (bwrap/User-Namespaces, Install-/
  Launcher-Lifecycle, GitHub-Checkout-Netzzugriffe, tmux-abhängige
  Läuferfamilien) sowie die vorbestehenden `ensure_test_agent`-Baseline-Fehler
  und der vorbestehende `agent_note`-NameError in `checkout_from_github`
  (`bin/vibe`).

Der Volllauf wird deshalb nicht als grün gewertet; er belegt jedoch, dass
AP2-Korbat keine Regression gegenüber dem Ausgangsstand einführt.

### Review

Unabhängiges Review, Runde 1: `docs/reviews/AP2-Korbat-review-1.md`
— **Verdict: PASS** (0 Critical, 0 High, 0 Medium, 1 Minor; der Minor-Befund
— ein veralteter Satz in dieser Datei — ist im Rahmen der finalen
Dokumentationspflege behoben und blockiert das PASS nicht).

### Empirische Verifikation am echten opencode (offline, isoliertes HOME)

`opencode debug agents --standalone` (v2.3.0, keine Modellaufrufe):

- `permissions`-Regelblöcke in Agenten-Markdowns werden gelesen; aufgelöste
  Regelreihenfolge: Basispolitik → globale Inline-Konfiguration
  (`OPENCODE_CONFIG_CONTENT`) → Markdown-Regeln zuletzt. Eine Markdown-Regel
  `subagent * allow` schlägt daher globale Inline-Deny-Regeln — globale Denys
  sind kein funktionierender Sperrmechanismus, deshalb `disabled`.
- `agents.<name>.disabled = true` (v2-`agents`-Map) entfernt `general`/`explore`
  aus dem Agenten-Katalog; die Legacy-`agent`-Map ignoriert `disabled`
  (deshalb schreibt der Läufer `disabled` ausschließlich in die `agents`-Map).
- `agents.<name>.model` überschreibt das Modell der Built-ins (in beiden Maps
  wirksam; `explore | model: opencode/deepseek-v4.1-flash-free` belegt).

## Grenzen

- Der projektbezogene Toggle und die Modellüberschreibung wirken in Läufen,
  die über `bin/vibe-run.sh` gestartet werden (Inline-Konfiguration). Ein
  manuell außerhalb von vibe gestartetes opencode in demselben Projekt
  erhält diese Inline-Konfiguration nicht. Das entspricht dem Ticket
  („if possible in a lean way … per project“) und dem bestehenden B1-Muster.
- Die Legacy-`agent`-Map in der Inline-Konfiguration ignoriert `disabled`
  (am echten opencode 2.3.0 verifiziert); `disabled` wird deshalb
  ausschließlich in die v2-`agents`-Map geschrieben. Das geprüfte
  Profil (`TESTED_VERSION`) bleibt 2.1.4; die Verifikation lief am
  installierten 2.3.0 (Fallback-Profil) plus offizieller V2-Dokumentation.
- `temperature` bleibt ein reines Editor-Feld der vibe-Oberfläche; opencode v2
  sendet es nicht an Modelle (wie zuvor; kein AP2-Verlust, aber auch keine
  neue Wirkung).
- Browser-Tests (Playwright) laufen in dieser Umgebung nicht; die
  Browser-Testdateien wurden nur mit `py_compile` geprüft.
- Die vorbestehenden Baseline-Fehler (`ensure_test_agent` fehlt in `bin/vibe`,
  `templates/common/.opencode/agents/test-agent.md` fehlt, `agent_note`
  NameError in `checkout_from_github`, bwrap nicht verfügbar) bleiben unberührt.
