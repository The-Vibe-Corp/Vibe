# AP2-Korbat — Bericht des unabhängigen Test-Agenten

## 1. Auftrag, Quellen und Vorgehen

Grundlage waren ausschließlich:

- Arbeitspaket AP2-Korbat in `TICKETS.md`,
- `SPEC.md` (Abschnitte Agenten, Modelle und Anbieter, Projekt-/Agentenverwaltung),
- `AGENTS.md` und `.vibe/project.env`,
- die im Auftrag festgehaltenen, empirisch verifizierten opencode-v2.3.0-Fakten
  und das dort beschriebene Soll-Verhalten A1–A9 / B1–B7.

Es existierte **keine Implementierung** für AP2-Korbat. Die Fälle wurden daher
aus dem Soll-Verhalten abgeleitet, nicht aus einem Diff. Produktionscode,
Konfiguration und Prüfskripte wurden nicht verändert.

Ausgangsstand: Branch `feature/korbat/ap2-korbat-2`, Basis-Commit `95b3790`.

## 2. Angelegte und geänderte Testdateien

### Neu

- `tests/unit/test_ap2_opencode_agents.py` — **64 Testmethoden** (A1–A9,
  B1–B4, B6, B7). Enthält lokale Parser-Helfer für v2-`permissions`-Blöcke,
  sodass die Tests nicht von einer bestimmten Feldreihenfolge abhängen.
  B6 nutzt die bestehende opencode-Attrappe aus `runner_support.py`; es werden
  keine Modellaufrufe ausgeführt.

### Angepasst (nur Tests)

- `tests/unit/test_agent_management.py`
- `tests/unit/test_ap03_agent_management.py`
- `tests/unit/test_ap8_github_checkout.py`
- `tests/unit/test_project_agents.py`
- `tests/unit/test_project_write_dirs.py`
- `tests/browser/test_ap03_agents_ui.py`
- `tests/browser/test_ap22_project_ui.py`
- `tests/browser/test_project_agents_ui.py`
- `tests/browser/test_write_dirs_ui.py`

## 3. Testfallliste

Die vollständige Liste steht als Testmethoden in der neuen Datei. Kurzform
(Name — Vorbedingung — Aktion — Erwartung):

### A1 — v2-Regeln in `permission_block`/`edit_permission_lines`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_voll_block_uses_v2_rules` | CLI geladen | `permission_block("voll")` | read/glob/grep/edit/shell allow; subagent/webfetch/websearch deny; keine `bash`/`task`/`list`-Schlüssel |
| `test_lesen_block_denies_write_shell_and_subagents` | — | `permission_block("lesen")` | read/glob/grep allow; edit/shell/subagent/webfetch/websearch deny |
| `test_lesen_git_block_orders_shell_rules_correctly` | — | `permission_block("lesen_git")` | shell: `*` deny zuerst, danach die vier Git-Allows in Reihenfolge |
| `test_project_full_block_denies_first_then_allows_each_write_dir` | Schreibverzeichnisse | `permission_block("voll", dirs)` | edit: `*` deny zuerst, dann je Dir `<dir>` und `<dir>/**` allow |
| `test_empty_write_dir_list_denies_edits` | leere Liste | dito | edit `*` deny |
| `test_edit_permission_lines_use_v2_list_items` | — | `edit_permission_lines([...])` | v2-Listenregeln mit Deny zuerst |

### A2 — `agent_template`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_template_frontmatter_is_v2_and_validates` | — | Template für lesen/voll/lesen_git | `permissions:`, keine v1-Schlüssel, `agent_validate` akzeptiert |
| `test_project_template_with_write_dirs_uses_v2_edit_rules` | Projekt mit Schreibrechten | Template `voll` + `write_dirs` | v2-Edit-Regeln, Deny zuerst, alle Dirs + `/**` allow, gültig |

### A3 — `agent_fields`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_fields_recognise_global_v2_presets` | v2-Templates | `agent_fields("global", text)` | erkennt lesen/voll/lesen_git; `permissions` nicht in `unknown` |
| `test_fields_recognise_project_v2_preset_with_write_dirs` | Projekt-Dirs | dito für Projekt | erkennt `voll` |
| `test_v1_block_is_custom_but_file_stays_readable_and_editable` | v1-Block | `agent_fields`, dann Render ohne Rechteänderung | `permission=""`, `permission_custom=True`, v1-Block bleibt erhalten, Datei gültig |

### A4 — `agent_render_fields`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_render_replaces_a_v1_block_with_v2_and_keeps_unknown_fields` | v1-Block mit `color` | `permission="lesen"` | v2-Block, `color` und Prompt erhalten, gültig |
| `test_render_replaces_a_v2_block` | v2-`voll` | `permission="lesen"` | v2-`lesen`, keine v1-Reste |
| `test_unknown_permission_preset_is_rejected` | — | `permission="root"` | `ValueError` |

### A5 — `agent_task_policy`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_star_allow_means_all` | v2 `subagent * allow` | Policy lesen | `mode=all` |
| `test_star_deny_means_none` | v2 nur Deny | dito | `mode=none` |
| `test_deny_star_plus_named_allows_is_sorted_custom` | v2 Deny `*` + a/b allow | dito | `custom`, `["a","b"]` |
| `test_later_rules_win` | widersprüchliche Regeln | dito | spätere Regel gewinnt |
| `test_v1_permission_task_fallback_still_works` | v1 `task:` | dito | all/custom wie bisher |
| `test_generated_template_denies_subagents_by_default` | v2-Template | dito | `none` |

### A6 — `agent_render_task`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_allow_all_replaces_only_subagent_rules` | v2 `voll` | `allow_all=True` | nur subagent-Regeln ersetzt; übrige Regeln identisch |
| `test_no_allowed_agents_writes_subagent_deny` | v2-Template | `allowed=[]` | subagent `*` deny |
| `test_custom_agents_write_deny_star_and_sorted_allows` | v2-Template | `allowed=["b","a"]` | Deny `*` + a/b allow (sortiert) |
| `test_matching_v1_template_block_is_migrated_completely` | v1-Block exakt `lesen` | `allowed=["x"]` | kompletter v2-Block, keine v1-Schlüssel, subagent deny + x allow |
| `test_individual_v1_block_keeps_v1_task_syntax` | individueller v1-Block | `allowed=["x"]` | bleibt v1, `task:` wird v1 geschrieben, Policy custom x |

### A7 — Schreibverzeichnisse mit v2

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_v2_full_grants_write_and_v2_readonly_does_not` | v2 voll/lesen | `_edit_grants_write` | True/False |
| `test_rewrite_edit_block_changes_only_edit_rules` | v2 voll mit Dir | `_rewrite_edit_block` | nur edit-Regeln ersetzt, übrige identisch, gültig |
| `test_apply_write_dirs_rewrites_a_v2_project_agent` | v2-Projektagent | `apply_write_dirs` | v2-Edit-Regeln ersetzt, Backup vorhanden |
| `test_apply_write_dirs_to_project_skips_read_only_v2_agents` | ein schreibbarer, ein lesender v2-Agent | `apply_write_dirs_to_project` | nur schreibbarer geändert |
| `test_v1_blocks_stay_functional` | v1-Blöcke | Grants/Rewrite | v1 bleibt funktionsfähig |

### A8 — Hierarchie mit v2

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_v2_hierarchy_unknown_and_cycle_rules_unchanged` | v2-Agenten a↔b | `agent_validate_hierarchy` | unbekannt/Zyklus abgelehnt, ohne Rückkante erlaubt |
| `test_v2_self_call_allowed_for_subagent_but_not_for_vibe_agent` | v2-Selbstfreigabe | dito | gewöhnlicher Subagent erlaubt; Vibe-Agent abgelehnt |
| `test_primary_agents_stay_unavailable_as_subagents` | v2-primary | dito | „kein Subagent“ |

### A9 — mitgelieferte `opencode.json`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_templates_common_opencode_json_uses_v2_permissions` | Datei vorhanden | JSON lesen | `permissions`-Liste, `shell`, kein `permission`/`bash` |

### B1 — Projektkonfiguration Version 3

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_missing_file_defaults_to_version_3_with_both_opencode_agents` | keine Datei | `project_agents_load` | Version 3; general/explore aktiv, Modell leer; nicht in Startliste |
| `test_version_2_is_migrated_with_opencode_defaults` | Version 2 | dito | Version 3 + opencode-Defaults |
| `test_valid_version_3_roundtrip` | Version 3 | dito | Werte bleiben erhalten |
| `test_unknown_opencode_agent_name_is_rejected` | `opencode.build` | dito | `ValueError` mit `build` |
| `test_unknown_opencode_entry_field_is_rejected` | `farbe` | dito | `ValueError` mit `farbe` |
| `test_aktiv_must_be_a_json_boolean` | `"aktiv": "ja"` | dito | `ValueError` |
| `test_modell_must_be_a_string_and_a_valid_model_pattern` | Zahl/Leerzeichen | dito | `ValueError` |
| `test_start_agent_list_rejects_opencode_agents` | `aktiv: ["general"]` | dito | `ValueError` |
| `test_unknown_top_level_field_is_rejected` | `farbe` | dito | `ValueError` |

### B2 — `project_agent_rows`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_rows_include_general_and_explore_with_marker` | globale Agenten | `project_agent_rows` | general/explore mit `opencode=True`, Default aktiv, Modell leer |
| `test_opencode_rows_reflect_toggle_and_effective_model` | opencode general aus, explore Modell | dito | `configured/selected` und `effective_model` korrekt |
| `test_opencode_rows_are_not_file_agents` | — | Inventory/`agent_read` | nicht im Datei-Inventar, nicht lesbar |

### B3 — `project_agent_set`

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_toggle_changes_only_the_opencode_section` | globale Agenten | `selected=False` für general | nur opencode-Abschnitt, Startliste unverändert, andere Projekte/Agentendateien unberührt |
| `test_model_is_stored_and_can_be_cleared_without_changing_aktiv` | general aus | Modell setzen/leeren | Modell gespeichert/geleert, `aktiv` bleibt False |
| `test_invalid_values_are_rejected_without_writing` | — | ungültige Werte | `ValueError`, keine Datei |
| `test_unknown_opencode_agent_is_rejected` | — | `agent="build"` | `ValueError` |
| `test_concurrent_change_is_refused` | veralteter Digest | `project_agents_save` | `ConcurrentChangeError` |

### B4 — Web-API

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_get_contains_opencode_rows` | echter Webserver, isolierte Umgebung | GET `/api/project-agents` | general/explore mit `opencode=True` |
| `test_post_toggle_and_model_for_opencode_agent` | dito | POST Toggle/Modell | 200, Datei/API aktualisiert |
| `test_invalid_post_returns_400_without_writing` | dito | ungültige Payloads | 400, Datei unverändert |
| `test_agent_template_api_returns_v2_frontmatter` | dito | POST `/api/agent_template` | v2-Frontmatter |

### B7 — CLI

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_project_agents_cli_lists_opencode_state_and_model` | opencode general aus, explore mit Modell | `vibe project-agents proj` | Exit 0, beide Zeilen mit Zustand und Modell |

### B6 — Läufer

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_no_effective_entries_keeps_previous_b1_behaviour` | opencode aktiv/ohne Modell, kein `modelle`, gemeinsamer Server | Lauf | Exit 0, keine Inline-Konfiguration, gemeinsamer Server unverändert genutzt (Kontrolle) |
| `test_active_model_is_mixed_into_both_agent_maps` | opencode general + Projektmodell | Lauf | Modell in `agent` und `agents`; bisheriges `modelle`-Verhalten erhalten |
| `test_inactive_agent_disables_only_the_v2_agents_map` | general/explore inaktiv | Lauf | `agents.<name>.disabled=true`, nicht in Legacy-`agent` |
| `test_inactive_model_is_not_applied` | inaktiv mit Modell | Lauf | kein Modell, nur Deaktivierung |
| `test_existing_jsonc_config_is_merged_and_preserved` | bestehende JSONC-Konfiguration | Lauf | JSONC wird semantisch gemergt, Unbeteiligtes bleibt |
| `test_shared_server_is_not_reused_with_effective_opencode_entry` | wirksamer opencode-Eintrag, gemeinsamer Server | Lauf | `--standalone`, kein `--server` auf den gemeinsamen Server |
| `test_invalid_opencode_model_aborts_before_agent_start` | ungültiges Modell, Kennwort gesetzt | Lauf | Abbruch vor opencode, verständliche Meldung, kein Geheimnis im Log |
| `test_unreadable_project_config_aborts_before_agent_start` | kaputte `agents.json` | Lauf | Abbruch vor opencode (bestehendes Verhalten) |

## 4. Rotphase auf dem unveränderten Stand (`95b3790`)

### 4.1 Neues Testmodul

Befehl (gekürzt; produktive `VIBE_*`/`SANDBOX*`-Variablen der Laufumgebung
wurden entfernt):

```
env -u VIBE -u VIBE_INSTALL ... -u VIBE_UI_BIND ... \
  python3 -m unittest tests.unit.test_ap2_opencode_agents -v
```

Ergebnis: **Exit 1**, `Ran 64`, `FAILED (failures=38, errors=6)`.
Die zahlreichen Fälle sind erwartete Rotfälle; mehrere Subtest-Varianten
(A2 presets) zählen einzeln. Die 6 Errors entstehen, weil der alte Code
Version 3 ablehnt bzw. keine opencode-Zeilen kennt; sie sind ebenfalls
Rotfälle, keine Umgebungsfehler.

Beispielhafte, wörtliche Auszüge:

```
FAIL: test_template_frontmatter_is_v2_and_validates (preset='lesen')
AssertionError: True is not false : v1-Schlüssel 'permission:' wurde erzeugt
```

```
FAIL: test_star_allow_means_all
AssertionError: {'mode': 'none', 'allowed': []} != {'mode': 'all', 'allowed': []}
```

```
FAIL: test_matching_v1_template_block_is_migrated_completely
AssertionError: True is not false : v1-Schlüssel 'permission:' wurde erzeugt
```

```
FAIL: test_missing_file_defaults_to_version_3_with_both_opencode_agents
AssertionError: 2 != 3
```

```
FAIL: test_rows_include_general_and_explore_with_marker
AssertionError: 'general' not found in {'tester': ..., 'vibe-agent': ...}
```

```
FAIL: test_project_agents_cli_lists_opencode_state_and_model
AssertionError: 1 != 0 : Traceback ... ValueError: Unbekannte Felder in der Agentenauswahl: opencode
```

```
FAIL: test_active_model_is_mixed_into_both_agent_maps
AssertionError: None != 'free/general'
```

```
FAIL: test_get_contains_opencode_rows
AssertionError: 'general' not found in {'vibe-agent': ...}
```

### 4.2 Kontroll-/Ankerfälle (müssen schon vorher grün sein)

Folgende Tests waren auf dem Ausgangsstand grün und dürfen durch die
Implementierung nicht rot werden:

- `test_v1_permission_task_fallback_still_works` (v1-Fallback A5)
- `test_individual_v1_block_keeps_v1_task_syntax` (A6, individueller v1-Block)
- `test_v1_blocks_stay_functional` (A7)
- `test_v2_self_call_allowed_for_subagent_but_not_for_vibe_agent` (A8,
  F32-Invariante unabhängig von v2)
- `test_aktiv_must_be_a_json_boolean`, `test_modell_must_be_a_string_and_a_valid_model_pattern`,
  `test_start_agent_list_rejects_opencode_agents`, `test_unknown_top_level_field_is_rejected`
- `test_opencode_rows_are_not_file_agents`
- `test_invalid_values_are_rejected_without_writing`, `test_unknown_opencode_agent_is_rejected`
- `RunnerControlTest.test_no_effective_entries_keeps_previous_b1_behaviour`
  (**Exit 0 / 1 Test OK**) — belegt, dass Standard-opencode-Einträge ohne
  Modell/Deaktivierung das bisherige B1-Verhalten nicht verändern.
- `RunnerInvalidConfigTest.test_unreadable_project_config_aborts_before_agent_start`
- `WebApiTest.test_invalid_post_returns_400_without_writing`

### 4.3 Angepasste Bestandstests

| Befehl | Ergebnis |
|---|---|
| `python3 -m unittest tests.unit.test_project_agents tests.unit.test_agent_management -v` | Exit 1, `Ran 54`, `failures=8, errors=2` (davon 1 Failure + 1 Error vorbestehend `ensure_test_agent`) |
| `python3 -m unittest tests.unit.test_project_write_dirs -v` | Exit 1, `Ran 40`, `failures=17` (alle erwartete v2-Rotfälle) |
| `python3 -m unittest tests.unit.test_b1_project_agent_models tests.unit.test_f32_subagent_self_spawn tests.unit.test_ap03_agent_management -v` | Exit 1, `Ran 77`, `failures=2, errors=5` — 2 erwartete Version-3-Rotfälle, 5 vorbestehende `ensure_test_agent`-Fehler; B1 und F32 vollständig grün |
| `python3 -m unittest tests.unit.test_ap03_agent_management tests.unit.test_ap8_github_checkout.AgentRemapTest -v` | Exit 1, `Ran 33`, `failures=2, errors=6` — 2 erwartete Version-3-Rotfälle, 5 vorbestehende `ensure_test_agent`-Fehler, 1 vorbestehender `agent_note`-NameError |

Wörtliche Beispiele:

```
FAIL: test_default_selection_uses_the_vibe_agent_and_opencode_agents
AssertionError: Lists differ: ['tester', 'vibe-agent'] != ['explore', 'general', 'tester', 'vibe-agent']
```

```
FAIL: test_model_override_is_independent_of_selection
AssertionError: 2 != 3
```

```
FAIL: test_version_1_is_migrated_to_version_3_without_losing_overrides
AssertionError: 2 != 3
```

## 5. Anpassungen an Bestandstests (je eine Begründung)

| Datei / Test | Anpassung | Begründung |
|---|---|---|
| `tests/unit/test_agent_management.py` `test_structured_fields_preserve_unknown_frontmatter_fields`, `test_render_adds_a_permission_block_when_the_file_has_none` | v1-Erwartungen (`permission:`/`read: allow`) durch v2-Erwartungen (`permissions:`/`action: read`/`action: edit`) ersetzt | Diese Tests schrieben die alte Generierung fest; das Soll ist v2. |
| `tests/unit/test_agent_management.py` `AgentApiTest.test_api_render_validates_and_never_writes` | Vorschau-Assertion auf `- action: read` | API liefert jetzt v2-Frontmatter. |
| `tests/unit/test_ap03_agent_management.py` `test_version_1_is_migrated_to_version_3_without_losing_overrides`, `test_model_override_is_independent_of_selection` | erwartete Version 2 → 3, Testname angepasst | B1 verlangt Projektdatei-Version 3; v1-Migration bleibt geprüft. |
| `tests/unit/test_project_agents.py` `test_default_selection...`, `test_project_local_agent...` | erwartete Zeilenmenge um `general`/`explore` ergänzt; `opencode=True`, Default aktiv, Modell leer geprüft | B2 liefert die opencode-Zeilen zusätzlich; sie sind keine Startagenten. |
| `tests/unit/test_project_agents.py` `test_deselected_agent...`, `test_unknown_config_keys...`, `test_non_string_model...`, `test_concurrent_change...` | Version 2 → 3 in Datei und Save-Daten | Version 3 ist das neue Schema. |
| `tests/unit/test_project_write_dirs.py` Fixtures `AGENT_TEMPLATE`/`AGENT_WITHOUT_EDIT`, Template-, Copy- und API-Tests | Fixtures auf v2 umgestellt, Assertions auf `permissions`/`action`/`effect` und Reihenfolge Deny-vor-Allow | Neu erzeugte Blöcke müssen v2 sein; v1 fällt nur noch als Eingabe/Kompatibilität an. |
| `tests/unit/test_ap8_github_checkout.py` `test_without_agents_file_the_default_selection_stays_active` | erwartete konfigurierte Namen um `general`/`explore` ergänzt | B2 markiert die opencode-Agenten standardmäßig als aktiv; Startagent bleibt der Vibe-Agent. |
| `tests/browser/test_ap03_agents_ui.py` zwei `agents_config()["version"]`-Assertions | 2 → 3 | Browser prüft dieselbe Projektdatei. |
| `tests/browser/test_project_agents_ui.py` bestehender Versionstest | 2 → 3; Testname angepasst | dito. |
| `tests/browser/test_project_agents_ui.py` neuer Fall `test_opencode_agents_are_marked_toggleable_and_keep_state` | neuer B5-Fall | OpenCode-Marker, Toggle, Modell, Reload. |
| `tests/browser/test_ap22_project_ui.py` neuer Fall `test_opencode_team_agents_are_marked_toggleable_and_persisted` | neuer B5-Fall (nova) | dito im `nvpTeamSection`. |
| `tests/browser/test_write_dirs_ui.py` Fixtures und zwei Fälle | v1-Fixtures/Assertions auf v2 umgestellt | Der Editor/die Anwendung erzeugt v2-Berechtigungen. |

**Bewusst nicht angepasst** (und begründet):

- `tests/unit/test_f32_subagent_self_spawn.py` und `tests/browser/test_f32_subagent_self_spawn_ui.py`:
  verwenden v1-Blöcke als **Eingabe** für den geforderten v1-Fallback (A5/A6);
  ihre `task:`-Assertions bleiben gültig.
- `tests/unit/test_ap03_agent_management.py` `task_agent` und die
  Render-Tests: individueller v1-Block muss laut A6 weiter v1 bleiben.
- `tests/browser/test_agents_ui.py`, `test_ap17_agent_roles_ui.py`,
  `test_ap22_agents_ui.py`: keine Assertion auf **neu erzeugte** v1-Syntax;
  v1-Fixtures sind weiterhin zulässige Eingaben.
- `tests/unit/test_b1_project_agent_models.py`: vollständig grün; B1-Verhalten
  darf nicht verändert werden.
- `tests/unit/test_project_management.py` `test_shipped_test_agent_template_is_complete`:
  scheitert bereits auf dem Ausgangsstand an einer fehlenden Datei
  (`templates/common/.opencode/agents/test-agent.md`), nicht an AP2.

## 6. Ausgeführte Befehle und Exitcodes (Zusammenfassung)

Immer mit bereinigter Umgebung (`env -u VIBE ... -u VIBE_UI_BIND ... -u SANDBOX ...`),
damit weder produktives `HOME`/`VIBE` noch die produktive Bindung
`VIBE_UI_BIND=<redacted>` verwendet werden.

| Befehl | Exit | Beobachtung |
|---|---|---|
| `python3 -m unittest tests.unit.test_ap2_opencode_agents -v` | 1 | 64 Tests, 38 Failures, 6 Errors (Rotphase) |
| `python3 -m unittest tests.unit.test_project_agents tests.unit.test_agent_management -v` | 1 | 8 Failures, 2 Errors (davon 1/1 vorbestehend) |
| `python3 -m unittest tests.unit.test_project_write_dirs -v` | 1 | 17 Failures (erwartete v2-Rotfälle) |
| `python3 -m unittest tests.unit.test_b1_project_agent_models tests.unit.test_f32_subagent_self_spawn tests.unit.test_ap03_agent_management -v` | 1 | `Ran 77`, `failures=2, errors=5`: 2 erwartete Version-3-Rotfälle in AP03, 5 vorbestehende `ensure_test_agent`-Fehler; B1 und F32 vollständig grün |
| `python3 -m unittest tests.unit.test_ap03_agent_management tests.unit.test_ap8_github_checkout.AgentRemapTest -v` | 1 | 2 erwartete Rotfälle, 6 Fehler (5 vorbestehend, 1 vorbestehender NameError) |
| `python3 -m unittest tests.browser.test_project_agents_ui -v` (mit `PLAYWRIGHT_BROWSERS_PATH`) | 1 | `ModuleNotFoundError: No module named 'playwright'` — Browserlauf nicht möglich |

## 7. Vorbestehende Baseline-Fehler (nicht AP2)

Auf dem unveränderten Stand `95b3790` reproduzierbar, unabhängig von AP2:

1. `ensure_test_agent` fehlt in `bin/vibe`:
   - `tests.unit.test_project_agents.RunSelectionTest.test_cmd_run_aborts_when_the_test_agent_cannot_be_created` (Error)
   - `...test_cmd_run_ensures_the_independent_test_agent_for_an_existing_project` (Failure)
   - `tests.unit.test_ap03_agent_management.VibeRunGateTest` (5 Errors)
2. `tests.unit.test_project_management.TemplateRulesTest.test_shipped_test_agent_template_is_complete`
   scheitert an fehlender Datei `templates/common/.opencode/agents/test-agent.md`.
3. `tests.unit.test_ap8_github_checkout` scheitert in `checkout_from_github`
   an `NameError: name 'agent_note' is not defined` (Zeile 2828 in `bin/vibe`).
4. `tests.unit.test_ap03_agent_management` enthält zusätzlich den
   `ensure_test_agent`-Block; die konkreten Zeilen sind in Abschnitt 4.3 belegt.

Diese Fehler wurden **nicht** behoben (keine Produktionsänderung durch den
Test-Agenten) und nicht als AP2-Nachweis gewertet.

## 8. Grenzen und offene Punkte

- **Browserabnahme nicht ausgeführt.** In der Laufumgebung ist das Python-Modul
  `playwright` nicht installiert; der Aufruf endet bereits beim Import mit
  `ModuleNotFoundError`. Die Browserfälle sind geschrieben und syntaktisch
  geprüft (`py_compile`), aber **nicht** als ausgeführtes Verhalten belegt.
  Das muss in einer Umgebung mit Playwright nachgeholt werden.
- **Keine Grünphase möglich**, weil die Implementierung noch fehlt. Nach der
  Implementierung ist die neue Datei plus die betroffenen Bestandstests erneut
  auszuführen; insbesondere die Browserfälle.
- **`test_ap8_github_checkout`** ist durch einen vorbestehenden `agent_note`-
  Fehler blockiert; die Anpassung konnte nicht bis zur eigentlichen Assertion
  ausgeführt werden.
- **UI-Vertrag „OpenCode-Kennzeichnung“** ist als sichtbarer Text/Atrribut
  `opencode` in der jeweiligen Zeile festgelegt. Der Coding-Agent muss diese
  Kennzeichnung in `projectAgentsCard` und `nvpTeamSection` ergänzen.
- **Version-3-Schema**: Die Tests erwarten normalisierte `opencode`-Einträge
  mit `aktiv` und `modell` (leer = geerbt). Ein leeres Modell entfernt nur den
  Modellwert, nicht den Agenten-Zustand.
- **Web-API/CLI** wurden gegen den echten `vibe-web.py` bzw. das CLI in
  temporären Verzeichnissen ausgeführt; Modellaufrufe fanden nicht statt
  (opencode-Attrappe).

## 9. Übergabe an Coding- und Review-Agenten

- Neue Testdatei: `tests/unit/test_ap2_opencode_agents.py` (64 Fälle).
- Angepasste Bestandstests: siehe Abschnitt 5.
- Erwarteter Testbefehl nach der Implementierung:
  `python3 -m unittest tests.unit.test_ap2_opencode_agents -v`
  sowie die betroffenen Module aus `.vibe/project.env`.
- Rotphase: dokumentiert in Abschnitt 4; Kontrollfälle in 4.2.
- Offene Nachweise: Browserfälle (Playwright fehlt) und die vorbestehenden
  Baseline-Fehler aus Abschnitt 7.

## 10. Nachtrag: Korrektur eines Testdefekts (A7, ein Fall)

Nach Verifikation durch den Coding-Agenten und den Auftraggeber wurde
**genau ein** Fall korrigiert:

- Datei: `tests/unit/test_ap2_opencode_agents.py`
- Fall: `A7WriteDirsTest.test_apply_write_dirs_to_project_skips_read_only_v2_agents`
- Zeile der Korrektur: `self.cli.write_dirs_save("proj", ["/tmp/neu"])`
  (vor `apply_write_dirs_to_project`), aktuell Zeile 814.

**Defekt:** Das Fixture legt keine `.vibe/permissions.json` an. Ohne diese
Datei liefert `write_dirs("proj")` die Standardliste
`[normalize_dir("/tmp/opencode"), os.path.realpath(project)]`; die Assertion
`self.assertIn("/tmp/neu", ...)` war damit in diesem Szenario unerfüllbar.

**Korrektur:** Der Fall setzt die Projektliste ausdrücklich auf `["/tmp/neu"]`.
Damit prüft er weiterhin den fachlichen Zweck: `apply_write_dirs_to_project`
aktualisiert den schreibbaren Agenten und lässt den Nur-Lese-Agenten
unverändert.

**Rot-Ergebnis nach der Korrektur** (unveränderter Produktcode):

```
test_apply_write_dirs_rewrites_a_v2_project_agent ... FAIL
test_apply_write_dirs_to_project_skips_read_only_v2_agents ... ok
test_rewrite_edit_block_changes_only_edit_rules ... FAIL
test_v1_blocks_stay_functional ... ok
test_v2_full_grants_write_and_v2_readonly_does_not ... ok
Ran 5 tests ... FAILED (failures=2)
```

Der korrigierte Fall selbst ist auf dem Ausgangsstand **grün**, weil die
projektweite Anwendung für v1-Blöcke bereits funktioniert; die Klasse bleibt
über die beiden echten v2-Rotfälle rot. Die früheren Gesamtzahlen der
Rotphase enthielten diesen defekten Fall und sind daher um einen Failure
niedriger zu lesen.

### 10.1 Zweiter Nachtrag: Setup-Defekt in einer angepassten Bestandstestdatei

Nach Verifikation durch den Coding-Agenten und den Auftraggeber wurde ein
weiterer Fall korrigiert:

- Datei: `tests/unit/test_project_write_dirs.py`
- Fall: `WriteDirsModelTest.test_apply_write_dirs_to_project_skips_agents_without_write_permission`
  (aktuell Zeile ~419/425)
- Änderung: vor `apply_write_dirs_to_project("proj")` wird
  `self.cli.write_dirs_save("proj", ["/tmp/opencode"])` gesetzt.

**Ursache:** Die Anpassung hatte die früher toleranten Assertions durch eine
exakte Drei-Elemente-Liste ersetzt:
`[("*", "deny"), ("/tmp/opencode", "allow"), ("/tmp/opencode/**", "allow")]`.
Das Fixture legt aber keine `.vibe/permissions.json` an; `write_dirs("proj")`
liefert dann die Standardliste (inkl. realpath des Projekts). Die
umgeschriebene Datei enthält deshalb vier Allow-Regeln, die exakte Liste war
so nicht erfüllbar. Es war derselbe Fehlertyp wie beim A7-Fall (Assertion ohne
passendes Setup).

**Korrektur:** Die Projektliste wird ausdrücklich auf `["/tmp/opencode"]`
gesetzt. Die exakte Assertion bleibt damit sinnvoll und prüft weiterhin
Deny-zuerst sowie die Reihenfolge der Verzeichnis-Allows.

**Ergebnis nach der Korrektur** (Implementierung liegt vor):

```
Ran 40 tests in 14.485s

OK
```

Der korrigierte Fall selbst:
`test_apply_write_dirs_to_project_skips_agents_without_write_permission ... ok`.

Außer diesem einen Fall und diesem Nachtrag wurde nichts geändert.
