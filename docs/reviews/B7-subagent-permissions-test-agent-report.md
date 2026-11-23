# B7 — Bericht des unabhängigen Test-Agenten

Arbeitspaket: B7 „Generation of agent file subagent permissions does not work
correctly for new opencode v2“ (FEEDBACK.md)
Repository/Arbeitskopie: `/var/log/custom/vibe-dev/worktrees/vibe-B7-Owlqs4`
Branch: `feature/korbat/b7`
Stand der Prüfung: 2026-11-23, Ausgangscommit `8931f7b`

## Angelegte Dateien

| Datei | Inhalt |
| --- | --- |
| `tests/unit/test_b7_subagent_permissions.py` | 21 Testmethoden (davon 2 mit Subtest-Schleifen: 2 v2-Eingabevarianten, 3 Vorlagen), ausschließlich temporäre VIBE-/HOME-/State-Pfade, opencode nur als Attrappe |
| `docs/reviews/B7-subagent-permissions-test-agent-report.md` | dieser Bericht |

Hinweis zum Ablageort: Der beauftragte Pfad `docs/reviews/B7-test-agent-report.md`
gehört bereits einem früheren Arbeitspaket „B7“ (GitHub-Authentifizierung über
die UI) und wurde unverändert belassen. Dieser Bericht liegt deshalb unter dem
eindeutigen Namen `B7-subagent-permissions-test-agent-report.md`.

Es wurden **keine** Produktivdateien (`bin/`, `templates/`), keine
Bestandstests und keine sonstigen Dokumente geändert.

## Testfälle

### Gruppe 1 — `RenderFieldsSubagentPolicyTest` (Serverpfad von Speichern und Vorschau)

Vorbedingung jeweils: Agentendatei im temporären globalen Agentenordner;
Aktion: `agent_render_fields("global", text, {"permission": <Vorlage>})`;
Erwartung: nur die Nicht-subagent-Regeln kommen aus der Vorlage, die
Subagenten-Regeln geben die Policy der **Eingabedatei** wieder.

| Testfall | Vorbedingung | Aktion | Erwartetes Ergebnis |
| --- | --- | --- | --- |
| `test_v1_task_allow_survives_preset_application` | v1-Datei mit `task: allow` (produktionsnaher Fall) | Vorlage `voll` | v2-Block, Policy `all`, `subagent * allow` vorhanden, übrige Regeln = `voll`, Prompt erhalten |
| `test_v1_custom_task_map_survives_preset_application` | v1 `task: {"*": deny, "vibe-coder": allow, "tester": allow}` | Vorlage `lesen` | Policy `custom` mit `["tester","vibe-coder"]`, Regeln `* deny`, `tester allow`, `vibe-coder allow` (sortiert) |
| `test_v2_subagent_rules_survive_preset_application` (2 Subtests) | v2-Datei mit `subagent * deny` + 2 Freigaben bzw. `subagent * allow` | Vorlage `lesen_git` | Subagenten-Regeln unverändert, übrige Regeln = `lesen_git` (inkl. 4 Git-Lesebefehle) |
| `test_v2_without_subagent_rules_gets_template_default_deny` | v2 nur `read`/`edit` | Vorlage `lesen` | genau `subagent * deny` (Charakterisierung) |
| `test_file_without_permission_block_gets_template_default_deny` | Datei ohne Rechteblock | Vorlage `voll` | neuer v2-Block, `subagent * deny` (Charakterisierung) |
| `test_v1_task_deny_stays_denied_under_preset` | v1 `task: deny` | Vorlage `voll` | weiterhin gesperrt, genau `* deny` (Schutzregel) |
| `test_v1_without_task_key_gets_template_default_deny` | v1-Block ohne `task` | Vorlage `lesen` | gesperrt, genau `* deny` (keine Freigabe erfunden) |
| `test_empty_permission_value_leaves_the_block_untouched` | v1 `task: allow` | `values` mit `permission: ""` + neuer Beschreibung | v1-Block bleibt v1, Subagenten bleiben erlaubt (Charakterisierung) |

### Gruppe 2 — `ExplicitSelectionTest` (Serverreihenfolge „erst Felder, dann Auswahl“)

| Testfall | Vorbedingung | Aktion | Erwartetes Ergebnis |
| --- | --- | --- | --- |
| `test_explicit_allowed_list_overrides_preset` | v1 `task: allow` | Vorlage `voll`, dann `agent_render_task(..., ["tester"])` | Policy `custom` mit genau `tester` |
| `test_explicit_allow_all_overrides_denied_preset` | v1 `task: deny` | Vorlage `lesen`, dann `allow_all=True` | genau `subagent * allow` |
| `test_explicit_empty_selection_denies_even_when_input_allowed` | v1 `task: allow` | Vorlage `voll`, dann `agent_render_task(..., [])` | genau `subagent * deny` |

### Gruppe 3 — `TemplateRegressionTest` (Arbeitspaket Punkt 4, Charakterisierung)

| Testfall | Vorbedingung | Aktion | Erwartetes Ergebnis |
| --- | --- | --- | --- |
| `test_agent_template_still_denies_subagents_by_default` | keine Datei | `agent_template` für alle drei Vorlagen, global und Projekt | Policy `none`, genau `subagent * deny` |
| `test_agent_render_task_without_preset_keeps_v1_syntax` | v1 individueller Block | `agent_render_task(..., ["x"])` ohne Vorlage | v1-`permission:` mit `task`-Einträgen bleibt (keine v2-Umstellung) |
| `test_agent_render_task_without_preset_replaces_only_subagent_rules_in_v2` | v2-Datei mit Subagenten-Regeln | `allow_all=True` ohne Vorlage | `* allow`, alle anderen Regeln unverändert |

### Gruppe 4 — `AgentApiTest` (echter HTTP-Weg über `bin/vibe-web.py`)

Server als Subprozess, isoliertes VIBE/HOME, opencode-Attrappe (2.1.4),
globaler Subagent `helper` für die Hierarchieprüfung. Payloads entsprechen
`bin/web/app.js`: `save` sendet nur geänderte strukturierte Felder plus
Prüfsumme, `render` alle Formularwerte.

| Testfall | Vorbedingung | Aktion | Erwartetes Ergebnis |
| --- | --- | --- | --- |
| `test_save_with_preset_and_without_task_fields_keeps_v1_task_allow` | v1 `task: allow` (`orchestrator`) | GET (Prüfsumme) + POST `action=save` mit `values:{permission:'voll'}`, **ohne** task-Felder | HTTP 200, v2-Datei, Policy `all`, `subagent * allow` vorhanden, übrige Regeln = `voll`, Antworttext = Datei |
| `test_render_with_full_ui_form_values_keeps_v1_task_allow` | v1 `task: allow` | POST `action=render` mit allen Formularwerten inkl. `permission:'voll'` | Vorschau mit Subagenten-Freigabe; Datei bytegleich unverändert |
| `test_save_with_preset_keeps_v1_custom_task_map` | v1-task-Map | GET + save mit `values:{permission:'lesen'}` | `* deny` + `tester allow` + `vibe-coder allow` |
| `test_save_with_preset_keeps_v2_subagent_rules` | v2 mit deny + 2 Freigaben | GET + save mit `values:{permission:'voll'}` | Subagenten-Regeln unverändert, übrige Regeln = `voll` |
| `test_save_with_explicit_task_all_wins_over_preset` | v1 `task: deny` | save mit Vorlage `lesen` + `task_all=true` | Policy `all` (Charakterisierung) |
| `test_save_with_explicit_allowed_list_wins_over_preset` | v1 `task: allow`, globaler Agent `helper` | save mit Vorlage `voll` + `task_allowed:["helper"]` | `* deny` + `helper allow` (Charakterisierung) |
| `test_template_api_still_denies_subagents` | keine Datei | POST `/api/agent_template` mit `perm:'voll'` | `subagent * deny` (Charakterisierung) |

## Rotphase (am unveränderten Stand tatsächlich ausgeführt)

Befehl:

```
python3 -m unittest tests.unit.test_b7_subagent_permissions -v
```

Beobachtetes Ergebnis:

```
Ran 21 tests in 1.108s
FAILED (failures=8)
```

Die 8 Fehlschläge sind genau die Soll-Fälle der Punkte 1–3; sie scheitern an
der Subagenten-Policy, nicht an der Testumgebung:

| Fall | Beobachtet (Istem) | Erwartet (Soll) |
| --- | --- | --- |
| `RenderFieldsSubagentPolicyTest.test_v1_task_allow_survives_preset_application` | `{'mode': 'none', 'allowed': []}` | `{'mode': 'all', 'allowed': []}` |
| `RenderFieldsSubagentPolicyTest.test_v1_custom_task_map_survives_preset_application` | Policy `none` | Policy `custom`, `['tester', 'vibe-coder']` |
| `RenderFieldsSubagentPolicyTest.test_v2_subagent_rules_survive_preset_application` (Subtest „ausgewaehlte“) | `[('*', 'deny')]` | `[('*', 'deny'), ('tester', 'allow'), ('vibe-coder', 'allow')]` |
| `RenderFieldsSubagentPolicyTest.test_v2_subagent_rules_survive_preset_application` (Subtest „alle“) | `[('*', 'deny')]` | `[('*', 'allow')]` |
| `AgentApiTest.test_save_with_preset_and_without_task_fields_keeps_v1_task_allow` | HTTP 200, aber Policy `none` | Policy `all`, `subagent * allow` |
| `AgentApiTest.test_render_with_full_ui_form_values_keeps_v1_task_allow` | Vorschau-Policy `none` | Vorschau-Policy `all` |
| `AgentApiTest.test_save_with_preset_keeps_v1_custom_task_map` | `[('*', 'deny')]` | `[('*', 'deny'), ('tester', 'allow'), ('vibe-coder', 'allow')]` |
| `AgentApiTest.test_save_with_preset_keeps_v2_subagent_rules` | `[('*', 'deny')]` | `[('*', 'deny'), ('tester', 'allow'), ('vibe-coder', 'allow')]` |

Damit ist der gemeldete Fehler unabhängig reproduziert: Eine angewendete
Rechte-Vorlage ersetzt den gesamten Rechteblock und setzt `subagent * deny`,
obwohl die Eingabedatei Subagenten erlaubte — über `agent_render_fields`
(GUI-Speichern) **und** über `render` („In Rohtext übernehmen“) sowie über
den echten HTTP-Endpunkt.

## Grüne Fälle (Charakterisierung / Schutzregeln)

Am unveränderten Stand grün (13 Methoden bzw. 14 inkl. Subtest-Zählung):

* `RenderFieldsSubagentPolicyTest`: `test_v2_without_subagent_rules_gets_template_default_deny`,
  `test_file_without_permission_block_gets_template_default_deny`,
  `test_v1_task_deny_stays_denied_under_preset`,
  `test_v1_without_task_key_gets_template_default_deny`,
  `test_empty_permission_value_leaves_the_block_untouched`
* `ExplicitSelectionTest`: alle drei Fälle (`task_allowed`/`task_all`/leere
  Auswahl gewinnen bereits heute, weil `agent_render_task` nach den Feldern
  läuft)
* `TemplateRegressionTest`: alle drei Fälle (`agent_template` erzeugt weiter
  `subagent * deny`; `agent_render_task` ohne Vorlage unverändert)
* `AgentApiTest`: `test_save_with_explicit_task_all_wins_over_preset`,
  `test_save_with_explicit_allowed_list_wins_over_preset`,
  `test_template_api_still_denies_subagents`

Sie sichern ab, dass die Korrektur nicht über das Ziel hinausschießt (keine
erfundenen Freigaben, ausdrückliche Auswahl bleibt stärker, Neuanlage bleibt
gesperrt).

## Kontrollregression (nur ausgeführt, nicht geändert)

Befehl:

```
python3 -m unittest tests.unit.test_ap2_opencode_agents tests.unit.test_agent_management tests.unit.test_ap03_agent_management -v
```

Beobachtetes Ergebnis: `Ran 124 tests ... OK` (Exit 0), sowohl vor als auch
nach dem Anlegen des neuen Moduls.

Bestandsfälle mit Bezug zu `agent_render_fields`/Rechten, die unverändert
bleiben und nach der Implementierung erneut laufen müssen:

* `test_ap2_opencode_agents`: `A1PermissionBlockTest` (Vorlageninhalt),
  `A2TemplateTest`, `A3FieldsTest` (v2-Presets erkannt, v1-individuell bleibt),
  `A4RenderFieldsTest` (v1→v2-Ersetzung, v2-Ersetzung, unbekannte Vorlage),
  `A5TaskPolicyTest` (Policy-Parsing inkl. v1-Fallback),
  `A6RenderTaskTest`, `A7WriteDirsTest`, `A8HierarchyTest`.
* `test_agent_management`: `StructuredEditorTest`
  (`test_structured_fields_preserve_unknown_frontmatter_fields`,
  `test_render_adds_a_permission_block_when_the_file_has_none`,
  `test_invalid_structured_values_are_rejected_before_writing`),
  `AgentApiTest` (`test_api_render_validates_and_never_writes`,
  `test_api_save_applies_changed_structured_values`).
* `test_ap03_agent_management`: `HierarchyTest`, `AgentApiTest`
  (`test_api_save_accepts_result_task_allowed_and_role`).

Eigene Prüfung dieser Fälle: In allen verwenden die Eingabedateien keine
Subagenten-Freigabe (kein `task`-Eintrag bzw. `task: deny`), sodass die
Soll-Korrektur dort weiterhin `subagent * deny` ergibt; die Fälle bleiben
voraussichtlich grün. Das ist eine Analyse, kein Ersatz für den erneuten Lauf.

## Weitere tatsächlich ausgeführte Prüfungen

```
python3 -m py_compile tests/unit/test_b7_subagent_permissions.py   # ok
python3 scripts/check-import-manifest.py                            # OK: 71 Dateien
python3 scripts/check-syntax.py                                     # OK: 243 Python-, 8 Bash-, 4 JSON-Dateien
python3 scripts/check-no-secrets.py                                 # OK: keine Geheimnisse
```

Die vollständige Paket-/Vollprüfung (`bash scripts/verify.sh package|full`)
wurde nicht ausgeführt: Sie schließt das neue Modul ein und muss in der
Rotphase zwangsläufig fehlschlagen; sie gehört nach der Implementierung zum
Lauf des Koordinators.

## Grenzen und offene Punkte

1. **Kein JS-/Browserlauf.** Die klassische UI (`bin/web/app.js`) wurde nur
   gelesen; die `taskChanged`-Logik und der Klickpfad wurden nicht im Browser
   ausgeführt. Die Payload-Sequenzen (GET-Prüfsumme → `save` mit nur
   geänderten Feldern; `render` mit allen Formularwerten) sind serverseitig
   exakt nachgestellt. Ein Browserfall in `tests/browser/` war nicht Teil des
   Arbeitsauftrags (eine neue Testdatei, vorgegebener unittest-Befehl).
2. **Nur globaler Scope.** Subagenten-Rechte lassen sich über die API nur für
   systemweite Agenten setzen (`scope != global` wird abgelehnt), die UI
   erzwingt `global`. Ob `agent_render_fields` für Projektagenten mit
   v1-`task`-Einträgen dieselbe Erhaltungsregel anwenden soll, ist im
   Arbeitspaket nicht ausdrücklich gefordert und daher nicht getestet.
3. **Repräsentation bei „alle“.** Für eine Eingabe mit `task: allow` fordert
   das Arbeitspaket eine `subagent`-Regel `* allow`. Der Test prüft die
   wirksame Policy **und** die Existenz dieser Regel, nicht die Abwesenheit
   einer zusätzlichen `* deny`-Zeile (eine `deny`+`allow`-Folge wäre
   wirkungsgleich). Für `custom` ist die im Arbeitspaket genannte Form
   (`* deny` plus sortierte Freigaben) exakt geprüft.
4. **„Unverändert“ bei v2-Regeln.** Der Test verwendet die kanonische
   Reihenfolge (`* deny`, dann sortierte Freigaben), sodass sowohl exaktes
   Erhalten als auch ein normalisiertes Neuschreiben die Prüfung besteht.
   Nicht-kanonische Reihenfolgen in Bestandsdateien sind nicht abgedeckt.
5. **Folge für die UI-Anzeige (Produktentscheidung, nicht getestet).** Nach
   der Korrektur entspricht ein Block mit Vorlagen-Rechten plus
   Subagenten-Freigabe keiner Vorlage mehr; `agent_fields(...)["permission"]`
   ist dann leer („individuell“), während die Subagenten-Auswahl „alle“
   zeigt. Das ist eine plausible, aber im Arbeitspaket nicht geregelte
   Folge; die Tests erzwingen sie nicht.
6. **Kein Implementierungsdiff geprüft.** Die Fälle sind aus Arbeitspaket und
   Soll-Beschreibung abgeleitet. Die Ursachenanalyse des Orchestrierers wurde
   nur insoweit bestätigt, wie die Rotphase sie stützt (Vorlage ersetzt den
   gesamten Block; fehlende task-Felder bei unverändertem Select).
