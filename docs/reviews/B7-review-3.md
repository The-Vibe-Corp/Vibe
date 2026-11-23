# Review B7 (Subagenten-Rechte) — Runde 1 (2026-11-23)

Unveränderte Abschrift der Reviewer-Antwort (vibe-reviewer, unabhängig, read-only) auf das
Arbeitspaket B7 „Generation of agent file subagent permissions does not work correctly for new
opencode v2“ (Branch feature/korbat/b7, Ausgangscommit 8931f7b, Umsetzungsstand uncommittet im
Arbeitsbaum). Ablage als `B7-review-3.md`: Runden 1–2 dieses Namensraums gehören dem älteren
B7-Nummernkreis „GitHub-Authentifizierung“ (docs/features/B7.md, docs/reviews/B7-review-1/2.md)
und bleiben unangetastet; die Fortsetzung der Sequenz sorgt dafür, dass die
Abschlussschranke dieses Review als jüngstes bewertet.

---

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| Rechte-Vorlage und Subagenten-Rechte als unabhängige Dimensionen: Beim Anwenden einer Vorlage (`values.permission`) bleibt die Subagenten-Policy der Eingabedatei (v1 `task: allow`, v1-task-Map, v2-`subagent`-Regeln) erhalten | PASS | `bin/vibe:3731-3775` (`agent_render_fields`, `_subagent_policy_to_v2`) | `tests/unit/test_b7_subagent_permissions.py:457-519` (`RenderFieldsSubagentPolicyTest`: 3 Methoden inkl. 2 Subtests; Rotphase 4/8 FAILED belegt in `docs/reviews/B7-subagent-permissions-test-agent-report.md:88-100`, nach Implementierung 21/21 OK laut gelieferter Verifikation) |
| Ohne vorhandene Subagenten-Freigabe (`mode == "none"`: v1 `task: deny`, v1 ohne `task`, v2 ohne `subagent`-Regeln, Datei ohne Rechteblock) gilt weiterhin der Vorlagen-Standard `subagent * deny`, und der Block bleibt als reine Vorlage erkennbar | PASS | `bin/vibe:3744-3751` (Guard `subagent_policy["mode"] != "none"`), `bin/vibe:3246,3256,3270` (`PERMS`) | `tests/unit/test_b7_subagent_permissions.py:520-569` (4 Charakterisierungs-/Schutzfälle in `RenderFieldsSubagentPolicyTest`) sowie Bestandsvertrag `test_agent_management.StructuredEditorTest.test_render_adds_a_permission_block_when_the_file_has_none` (in den dokumentierten 124 OK-Tests enthalten) |
| Ausdrücklich im selben Request gesendete Subagenten-Auswahl (`task_all` / `task_allowed`) gewinnt weiterhin gegen Vorlage und Eingabe-Policy | PASS | `bin/vibe-web.py:2120-2172` (Serverreihenfolge `agent_render_fields` → `agent_render_task`), `bin/vibe:3967-3985` | `tests/unit/test_b7_subagent_permissions.py:595-660` (`ExplicitSelectionTest`, 3 Fälle) und `tests/unit/test_b7_subagent_permissions.py:1006-1057` (`AgentApiTest`, 2 HTTP-Fälle) |
| End-to-end über `/api/agent` (`action=save` und `action=render`) mit den Payload-Sequenzen der klassischen UI wirksam | PASS | `bin/vibe-web.py:2114-2122,2216-2220`, `bin/vibe:3718-3753` | `tests/unit/test_b7_subagent_permissions.py:897-1005` (`AgentApiTest`, 4 HTTP-Fälle gegen echten `vibe-web.py`-Subprozess; Rotphase 4/8 FAILED belegt in `docs/reviews/B7-subagent-permissions-test-agent-report.md:101-104`) |
| Neuanlage (`agent_template`, `/api/agent_template`) und `agent_render_task` ohne Vorlage bleiben unverändert | PASS | `bin/vibe:3967-4040` (`agent_render_task`), `bin/vibe:4597-4613` (`agent_template`) | `tests/unit/test_b7_subagent_permissions.py:667-734,1058-1073` (`TemplateRegressionTest`, `test_template_api_still_denies_subagents`) |
| Dokumentation (`docs/features/B7-subagent-permissions.md`, `docs/import-manifest.json`) und unabhängiger Testbericht (`docs/reviews/B7-subagent-permissions-test-agent-report.md`) vollständig und konsistent | PASS | `docs/features/B7-subagent-permissions.md:1-113`, `docs/import-manifest.json:1356-1381`, `docs/reviews/B7-subagent-permissions-test-agent-report.md:1-213` | Statische Prüfung des Diffs gegen `8931f7b`; `python3 scripts/check-import-manifest.py` → OK (71 Dateien, im Testbericht und vom Orchestrierer dokumentiert) |

## Findings
- No findings.

## Direkte Antworten auf die Prüfaufträge 1–6

### 1. Korrektheit der Implementierung gegen das Soll-Verhalten
- **Policy-Erfassung der EINGABE vor dem Überschreiben:** In `bin/vibe:3734-3743` wird `subagent_policy = agent_task_policy(text)` auf dem unveränderten Eingabetext `text` aufgerufen, **bevor** `_apply_agent_fields(text, clean, permission_lines)` in `bin/vibe:3743` den bestehenden `permission:`- bzw. `permissions:`-Block durch `permission_lines` ersetzt.
- **Behandlung aller Policy-Modi (`all`, `custom`, `none`):**
  - `mode == "none"`: Die Bedingung `if permission_lines is not None and subagent_policy["mode"] != "none":` (`bin/vibe:3744`) überspringt `_subagent_policy_to_v2`. Dadurch bleibt der von `_apply_agent_fields` geschriebene Vorlagenblock (inkl. `("subagent", "*", "deny")` an der Vorlagenposition `bin/vibe:3246,3256,3270`) bytegenau erhalten, sodass `agent_fields(scope, new_text)["permission"]` (`bin/vibe:3622-3628`) die Vorlage weiterhin über `_same_block` erkennt.
  - `mode == "all"`: `_subagent_policy_to_v2` (`bin/vibe:3755-3774`) entfernt alle `subagent`-Regeln aus dem Vorlagenblock (`bin/vibe:3771`) und hängt über `_subagent_rules(policy["allowed"], allow_all=True)` (`bin/vibe:3772,3959-3960`) `("subagent", "*", "allow")` an.
  - `mode == "custom"`: `_subagent_rules(policy["allowed"], allow_all=False)` (`bin/vibe:3772,3961-3964`) erzeugt `[("subagent", "*", "deny")] + [("subagent", name, "allow") for name in sorted(set(allowed))]`.
- **v1-Fallback, v2-Bestand, kein Block:** `agent_task_policy(text)` (`bin/vibe:3797-3853`) wertet bei vorhandenem v2-`permissions`-Block die `subagent`-Regeln nach „letzte passende Regel gewinnt“ aus (`_subagent_policy`, `bin/vibe:3776-3794`). Ohne v2-Block greift der v1-Fallback auf `permission:` mit `task: allow` (`mode: "all"`), `task: deny` (`mode: "none"`), individueller `task:`-Map (`mode: "custom"` mit sortierten `allow`-Einträgen bzw. `"all"` bei `"*": allow`) oder fehlendem `task` / fehlendem Rechteblock (`mode: "none"`).
- **Reihenfolge und Idempotenz:** Da die Nicht-`subagent`-Regeln der Vorlagen (`PERMS`, `bin/vibe:3239-3274`) und die `subagent`-Regeln disjunkte `action`-Mengen besitzen (`read`, `glob`, `grep`, `edit`, `shell`, `webfetch`, `websearch` vs. `subagent`), ist die Verschiebung der `subagent`-Regeln ans Ende des `permissions:`-Blocks (`bin/vibe:3771-3773`) semantisch äquivalent und identisch zum Verhalten von `agent_render_task` (`bin/vibe:3982-3984`). Ein erneuter Aufruf von `agent_render_fields` mit derselben Vorlage liest über `agent_task_policy` exakt dieselbe Policy und erzeugt denselben Block (idempotent).
- **Fehlerwege (unlesbares Frontmatter / Inline-Rechte):** Bei unlesbarem Frontmatter oder doppelten Top-Level-Schlüsseln wirft `agent_task_policy(text)` über `_frontmatter_parts(text)` (`bin/vibe:3508-3516,3806`) denselben `ValueError`, den zuvor `_apply_agent_fields` (`bin/vibe:3674`) geworfen hätte. Inline-Rechte (`permission: allow` oder `permissions: [...]`) werden weiterhin in `_apply_agent_fields` (`bin/vibe:3696-3699`) mit `ValueError` abgewiesen, bevor `_subagent_policy_to_v2` erreicht wird; der Guard `if v2 is None or v2["inline"]: return text` (`bin/vibe:3769-3770`) sichert die Hilfsfunktion zusätzlich defensiv ab.
- **CRLF-Behandlung:** `_subagent_policy_to_v2` ermittelt `sep = "\r\n" if "\r\n" in fm else "\n"` (`bin/vibe:3764`) und setzt den Text über `text[:m.start(1)] + sep.join(lines) + text[m.end(1):]` (`bin/vibe:3774`) zusammen — exakt wie `_apply_agent_fields` (`bin/vibe:3675`) und `agent_render_task` (`bin/vibe:3976,3985`).

### 2. Kollateraleffekte und Architektur
- **Verhältnis `_subagent_policy_to_v2` zu `agent_render_task`:** Die 5 Kernzeilen in `_subagent_policy_to_v2` (`bin/vibe:3763-3774`) äneln dem v2-Zweig von `agent_render_task` (`bin/vibe:3975-3985`), haben aber bewusst unterschiedliche Vorbedingungen: `agent_render_task` erzwingt bei `allow_all=False` eine strenge `NAME_RE`-Validierung auf `allowed` (`bin/vibe:3969-3974`) und behandelt außerdem v1-Blöcke und blocklose Dateien. `_subagent_policy_to_v2` wird dagegen ausschließlich nach dem Preset-Rendering aufgerufen (wo garantiert ein v2-Block vorliegt) und übernimmt die bereits aus der Bestandsdatei geparste `policy` ohne zusätzliche Eingabevalidierung. Die kleine, lokal gekapselte Hilfsfunktion entspricht den Projekt-Leitlinien (`AGENTS.md`, KISS / Clean Code: kleine Funktion mit einer klaren Aufgabe, keine spekulative Umstrukturierung von `agent_render_task`).
- **Zusammenspiel mit `bin/vibe-web.py` und `bin/web/app.js`:**
  - In `bin/vibe-web.py:2120-2121` läuft zuerst `vibe.agent_render_fields(scope, text, body.get("values"))`. Wenn die klassische UI (`bin/web/app.js:1613-1616`) wegen unveränderter Subagenten-Auswahl (`taskChanged == false`) weder `task_all` noch `task_allowed` sendet, bewahrt `agent_render_fields` nun die Subagenten-Policy der Eingabedatei.
  - Sendet die UI (oder ein API-Client) `task_all` (`bin/vibe-web.py:2147-2152`) oder `task_allowed` (`bin/vibe-web.py:2153-2172`), überschreibt der nachfolgende Aufruf `vibe.agent_render_task(...)` die `subagent`-Regeln des v2-Blocks gezielt mit der neuen Auswahl.
  - **Hierarchieprüfung und F32-Invariante:** Bei explizitem `task_allowed` prüft `vibe.agent_validate_hierarchy(an, task_allowed, own_text=text, vibe_agent=effective_vibe)` (`bin/vibe-web.py:2170-2171`) gegen den bereits von `agent_render_fields` erzeugten `own_text` (sodass eine gleichzeitige `mode`-Änderung im selben Request berücksichtigt wird). Unabhängig davon, ob `task_allowed` gesendet wurde oder die Freigabe aus der Bestandsdatei erhalten blieb, prüft die nachgelagerte F32-Invariante in `bin/vibe-web.py:2177-2188` abschließend `vibe.agent_task_policy(text)` darauf, dass der Vibe-Agent keine Selbstfreigabe (`policy["mode"] == "custom" and an in policy["allowed"]`) besitzt. Das ist lückenlos konsistent.

### 3. Bestandsverträge
- Keine bestehende Testdatei unter `tests/` wurde verändert oder abgeschwächt (`git status --short` zeigt ausschließlich ` tests/unit/test_b7_subagent_permissions.py` als neue Testdatei).
- **`agent_fields` / Vorlagenerkennung:** Für alle Dateien ohne Subagenten-Freigabe (`mode == "none"`) bleibt der generierte `permissions:`-Block unverändert, sodass `agent_fields(scope, text)["permission"]` (`bin/vibe:3622-3628`) weiterhin den Vorlagennamen liefert (wichtig für `test_render_adds_a_permission_block_when_the_file_has_none`). Für Dateien mit aktiver Subagenten-Freigabe (`mode in ("all", "custom")`) weicht der kombinierte Block von der reinen Vorlage ab und wird von `agent_fields` ehrlich als individuell (`permission: ""`, `permission_custom: True`) klassifiziert, während `agents_all()` (`bin/vibe:4130,4137-4138`) `task_mode` und `allowed_agents` aus `agent_task_policy(text)` liest und in der UI exakt anzeigt.
- **`agent_copy` / `_rewrite_edit_block`:** `_rewrite_edit_block` (`bin/vibe:4615-4626`) filtert in v2-Blöcken ausschließlich nach `rule.get("action") != "edit"` und hängt `_edit_rules(write_dirs)` an; erhaltene `subagent`-Regeln bleiben dabei unberührt.
- **`agent_role_set` (F32):** `agent_role_set` (`bin/vibe:3436-3452`) prüft `agent_task_policy(agent_read("global", name))` unverändert.

### 4. Sicherheits- und Geheimnisaspekte
- Keine Geheimnisse, Tokens oder produktiven Pfade in Code, Tests oder Dokumentation.
- `tests/unit/test_b7_subagent_permissions.py:65-128` bereinigt alle `VIBE_*`- und `HOME`-Umgebungsvariablen (`ISOLATED_ENV`) und richtet sowohl für die Unit-Tests (`CliFixture`, `tests/unit/test_b7_subagent_permissions.py:408-425`) als auch für den `vibe-web.py`-Subprozess (`AgentApiTest`, `tests/unit/test_b7_subagent_permissions.py:772-838`) isolierte `tempfile.TemporaryDirectory()`-Pfade und eine lokale Bash-Attrappe (`FAKE_OPENCODE`, `tests/unit/test_b7_subagent_permissions.py:740-748`) ein. Es finden keine echten `opencode`-, Modell-, OAuth- oder MCP-Aufrufe statt.
- Keine Veränderung an Verifikationsskripten (`scripts/*`) oder Baselines (`tests/verify-baseline.json`).

### 5. Dokumentation, Manifest und Test-Agent-Bericht
- **Feature-Dokumentation (`docs/features/B7-subagent-permissions.md:1-113`):** Beschreibt Ziel, beobachtetes Fehlverhalten, Ursache (`agent_render_fields` + `PERMS` + `taskChanged` in `app.js`), Umsetzung (`agent_task_policy` vorab, `_subagent_policy_to_v2` bei `mode != "none"`), Architekturentscheidungen (inkl. der kosmetischen Folge „individuell“ bei kombinierter Vorlage + Freigabe), ausgeführte Verifikationsbefehle und Grenzen präzise und ohne Widersprüche zum Code.
- **Import-Manifest (`docs/import-manifest.json:1356-1381`):** Der `files`-Eintrag für `bin/vibe` (`bytes: 309523`, `sha256: bc085a9aa9674e57f188357d7cba4e366d5a135ac0336dffc07a80891972aa4e`) und der neue `aenderungen`-Eintrag für `B7` sind vollständig und laut dokumentiertem Lauf `python3 scripts/check-import-manifest.py` valide.
- **Bericht des unabhängigen Test-Agenten (`docs/reviews/B7-subagent-permissions-test-agent-report.md:1-213`):** Dokumentiert alle 21 Testmethoden mit Vorbedingung, Aktion und erwartetem Ergebnis sowie das tatsächliche Rotphasen-Protokoll am Ausgangsstand `8931f7b` (`Ran 21 tests in 1.108s — FAILED (failures=8)` mit Gegenüberstellung Ist vs. Soll in Zeilen 95–104). Die Tests prüfen beobachtbares Verhalten und Verträge, nicht interne Hilfsfunktionsnamen (`_subagent_policy_to_v2` kommt im Testmodul nicht vor).

### 6. Scope-Disziplin und Ablagekonvention
- Der Änderungssatz umfasst ausschließlich die 5 zum Ticket B7 gehörenden Dateien (`bin/vibe`, `docs/import-manifest.json`, `tests/unit/test_b7_subagent_permissions.py`, `docs/features/B7-subagent-permissions.md`, `docs/reviews/B7-subagent-permissions-test-agent-report.md`).
- Die bestehenden Dateien des älteren B7-Nummernkreises (`docs/features/B7.md`, `docs/reviews/B7-review-1.md`, `docs/reviews/B7-review-2.md`, `docs/reviews/B7-test-agent-report.md`) blieben unangetastet; die Benennung `B7-subagent-permissions.md` bzw. `B7-subagent-permissions-test-agent-report.md` folgt dem etablierten Präzedenzfall aus B6 (`docs/features/B6-statusmarken.md`).

## Verification
- Change set reviewed: `8931f7b..working tree` (`bin/vibe`, `docs/import-manifest.json` modified; `docs/features/B7-subagent-permissions.md`, `docs/reviews/B7-subagent-permissions-test-agent-report.md`, `tests/unit/test_b7_subagent_permissions.py` untracked).
- Git commands run by me: `git status --short && git diff 8931f7b`.
- Checks evidenced by supplied raw output: `python3 -m unittest tests.unit.test_b7_subagent_permissions -v` (Rotphase `Ran 21 tests in 1.108s / FAILED (failures=8)` in `docs/reviews/B7-subagent-permissions-test-agent-report.md:82-104`, Grünphase `Ran 21 tests, OK`), `python3 -m unittest tests.unit.test_ap2_opencode_agents tests.unit.test_agent_management tests.unit.test_ap03_agent_management -v` (`Ran 124 tests, OK`), `python3 -m unittest tests.unit.test_f32_subagent_self_spawn tests.unit.test_project_agents tests.unit.test_b1_project_agent_models` (`Ran 70 tests, OK`), `python3 scripts/check-import-manifest.py` (`OK: 71 Dateien`), `python3 scripts/check-syntax.py` (`OK`), `python3 scripts/check-no-secrets.py` (`OK`), `bash scripts/verify.sh quick` (`Exit 0`), `bash scripts/verify.sh package` (`Exit 0`).
- Checks reported only by the coding agent: none beyond the checks documented in task output and reports (`bash scripts/verify.sh full` is explicitly noted as pending once before closure per `AGENTS.md`).
- Checks not independently run: all build, test, and other non-Git checks (read-only review).
- Important areas inspected: `bin/vibe` (lines 3236–4709), `bin/vibe-web.py` (lines 2105–2236), `bin/web/app.js` (lines 1580–1631), `docs/import-manifest.json`, `docs/features/B7-subagent-permissions.md`, `docs/reviews/B7-subagent-permissions-test-agent-report.md`, `tests/unit/test_b7_subagent_permissions.py`, `FEEDBACK.md`.
- Remaining risks: Einmaliger Volllauf (`bash scripts/verify.sh full`) vor Paketabschluss durch den Orchestrierer steht vereinbarungsgemäß noch aus.

Verdict: PASS
