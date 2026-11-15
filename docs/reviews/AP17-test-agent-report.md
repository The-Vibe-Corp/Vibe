# AP17 — Test-Agent-Bericht: Weitere Agentenrollen

- Datum: 2026-11-15
- Arbeitspaket: AP17 „Für Agents soll es weitere Rollen geben, welche explizit zugewiesen werden können: tester, analyst, sonstiges, content-creator.“
- Rolle: unabhängiger Test-Agent (Rotphase, keine Implementierung)
- Arbeitsverzeichnis: `/tmp/opencode/vibe-ap17`, Branch `feature/m0p/ap17-agent-roles`
- Erstellte Testdateien:
  - `tests/unit/test_ap17_agent_roles.py`
  - `tests/browser/test_ap17_agent_roles_ui.py`

Die Fälle sind aus AP17, den kontextualisierten Akzeptanzkriterien und `SPEC.md`
(Agenten, Modellprofile) abgeleitet. Es wurde keine Implementierung gelesen oder
verändert; die Produktionsdateien blieben unangetastet.

## Testfälle — Unit/Backend

### `RoleCatalogTest`

1. **`test_role_catalog_contains_existing_and_new_roles`**
   - Vorbedingung: `bin/vibe` ist mit isoliertem VIBE-/HOME-Zustandsordner geladen.
   - Aktion: `ROLE_NAMES` wird gelesen.
   - Erwartetes Ergebnis: `coder`, `reviewer`, `vibe` bleiben enthalten; zusätzlich
     sind `tester`, `analyst`, `sonstiges`, `content-creator` vorhanden. Es gibt
     keine weiteren Rollen.

2. **`test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json`**
   - Vorbedingung: Für jede neue Rolle existiert eine gültige globale Agentendatei.
   - Aktion: `agent_role_set` wird für alle vier neuen Rollen aufgerufen.
   - Erwartetes Ergebnis: Jede Rolle ist im Rückgabewert und in `profiles.json`
     unter `rollen` gespeichert.

3. **`test_new_roles_are_visible_in_the_agent_list`**
   - Vorbedingung: Vier globale Agenten tragen je eine neue Rolle.
   - Aktion: `agents_all()` wird ausgewertet.
   - Erwartetes Ergebnis: Jede globale Agentenzeile enthält ihre zugewiesene
     Rolle; die Rolle ist damit in der Agentenliste sichtbar.

4. **`test_unknown_role_is_rejected_without_changing_profiles_json`**
   - Vorbedingung: Ein globaler Agent hat die Rolle `coder`; `profiles.json` liegt vor.
   - Aktion: `agent_role_set` wird mit `supervisor`, `Tester`, `content_creator`
     und `vibe-agent` aufgerufen.
   - Erwartetes Ergebnis: Jeweils `ValueError`; `profiles.json` und die
     Agentendatei bleiben bytegleich.

5. **`test_new_roles_do_not_change_the_vibe_protection_rules`**
   - Vorbedingung: Ein Agent trägt `vibe`, ein zweiter Agent ist vorhanden.
   - Aktion: Der zweite Agent erhält `analyst`; danach wird versucht, dem letzten
     Vibe-Agenten die Rolle zu entziehen bzw. ihn umzuwidmen. Anschließend wird
     `vibe` auf den zweiten Agenten gesetzt.
   - Erwartetes Ergebnis: Die neue Rolle stört den Vibe-Agenten nicht. Entfernen
     und Umwidmen des letzten Vibe-Agenten bleiben verboten; genau ein Agent
     trägt `vibe`. Das Umsetzen durch gleichzeitige Zuweisung bleibt möglich.

### `TesterRolePreflightTest`

6. **`test_missing_tester_is_resolved_from_tester_role`**
   - Vorbedingung: `project.env` enthält keinen `TESTER`; `profiles.json` enthält
     die Rolle `tester` für einen verfügbaren Agenten.
   - Aktion: `preflight_errors` mit leerem `tester` und Zustandsordner.
   - Erwartetes Ergebnis: Keine Befunde; der Rollenagent übernimmt TESTER.

7. **`test_project_local_agent_file_satisfies_the_tester_role`**
   - Vorbedingung: Die globale Datei des Rollenagenten fehlt; dieselbe Agentendatei
     liegt im Projektordner.
   - Aktion: `preflight_errors` ohne expliziten TESTER.
   - Erwartetes Ergebnis: Keine Befunde; auch der Projektordner ist ein gültiger
     Agentenort.

8. **`test_stale_tester_role_entry_does_not_block_available_agent`**
   - Vorbedingung: `profiles.json` nennt zuerst einen nicht vorhandenen, danach
     einen verfügbaren Agenten mit Rolle `tester`.
   - Aktion: `preflight_errors` ohne expliziten TESTER.
   - Erwartetes Ergebnis: Keine Befunde; der verfügbare Rollenagent wird gewählt
     (analog zum REVIEWER-Fallback).

9. **`test_unavailable_tester_role_is_reported_with_its_name`**
   - Vorbedingung: Die Rolle `tester` zeigt auf einen Agenten, dessen Datei weder
     global noch im Projekt liegt.
   - Aktion: `preflight_errors` ohne expliziten TESTER.
   - Erwartetes Ergebnis: Ein TESTER-Befund nennt `veralteter-tester` und meldet
     die fehlende Agentendatei („nicht verfügbar“).

10. **`test_explicit_tester_argument_wins_over_the_tester_role`**
    - Vorbedingung: Die Rolle `tester` zeigt auf einen nicht vorhandenen Agenten;
      der als Argument übergebene Agent ist verfügbar.
    - Aktion: `preflight_errors(tester="test-agent")`.
    - Erwartetes Ergebnis: Keine Befunde; der ausdrückliche TESTER hat Vorrang.

11. **`test_unavailable_explicit_tester_blocks_despite_a_valid_role`**
    - Vorbedingung: Die Rolle `tester` zeigt auf einen verfügbaren Agenten.
    - Aktion: `preflight_errors(tester="nicht-vorhanden")`.
    - Erwartetes Ergebnis: Ein TESTER-Befund nennt `nicht-vorhanden`; die Rolle
      ersetzt ihn nicht.

12. **`test_project_env_tester_wins_over_the_tester_role`**
    - Vorbedingung: Die Rolle `tester` ist verfügbar; `project.env` setzt
      ausdrücklich einen nicht vorhandenen TESTER.
    - Aktion: `preflight_errors` ohne Argument.
    - Erwartetes Ergebnis: Der Befund nennt den Wert aus `project.env`; die Rolle
      wird nicht als Ersatz verwendet.

13. **`test_without_state_directory_missing_tester_still_blocks`**
    - Vorbedingung: `project.env` enthält keinen TESTER.
    - Aktion: `preflight_errors` ohne Zustandsordner.
    - Erwartetes Ergebnis: Der bisherige Befund `TESTER fehlt` bleibt bestehen.

14. **`test_missing_or_broken_profiles_file_blocks_with_tester_message`**
    - Vorbedingung: `project.env` enthält keinen TESTER.
    - Aktion: `profiles.json` wird entfernt bzw. mit ungültigem JSON gefüllt.
    - Erwartetes Ergebnis: Jeweils `TESTER fehlt`; kein Absturz.

15. **`test_reviewer_fallback_still_resolves_from_profiles_json`**
    - Vorbedingung: `project.env` enthält einen verfügbaren TESTER, aber keinen
      REVIEWER; `profiles.json` enthält die Rolle `reviewer`.
    - Aktion: `preflight_errors`.
    - Erwartetes Ergebnis: Keine Befunde; der REVIEWER-Fallback bleibt unverändert.

### `TesterRoleCliTest`

16. **`test_cli_preflight_resolves_tester_from_state_directory`**
    - Vorbedingung: `project.env` ohne TESTER; `profiles.json` im Zustandsordner
      enthält die Rolle `tester` für einen verfügbaren Agenten.
    - Aktion: `preflight --state <ordner>` wird als Subprozess ausgeführt.
    - Erwartetes Ergebnis: Rückgabewert 0, keine `BLOCKIERT`-Meldung.

17. **`test_cli_preflight_without_state_still_blocks_missing_tester`**
    - Vorbedingung: `project.env` ohne TESTER; kein Zustandsordner.
    - Aktion: `preflight` ohne `--state`.
    - Erwartetes Ergebnis: Rückgabewert 2 und eine TESTER-Meldung.

## Testfälle — Browser/Dashboard

1. **`test_01_role_select_offers_the_new_roles`**
   - Vorbedingung: Das echte Dashboard läuft auf eigenem Port; die Agentenliste
     zeigt den globalen Agenten `tester`.
   - Aktion: Die Optionen von `select[data-role="tester"]` werden gelesen.
   - Erwartetes Ergebnis: Die Werte enthalten `tester`, `analyst`, `sonstiges`,
     `content-creator` sowie weiterhin `coder`, `reviewer`, `vibe`.

2. **`test_02_tester_role_is_saved_and_shown_after_reload`**
   - Vorbedingung: Das Dashboard läuft; `tester` hat noch keine Rolle.
   - Aktion: Im Rollenauswahlfeld wird `tester` gewählt; danach wird die
     Agentenliste neu geöffnet.
   - Erwartetes Ergebnis: `profiles.json` enthält `tester: tester`; das
     Auswahlfeld zeigt nach dem Neuladen weiterhin `tester`.

## Rotphase — Unit

Befehl:

```
python3 -m unittest tests.unit.test_ap17_agent_roles -v
```

Ergebnis: 17 Tests, 6 Failures, 3 Errors. Die Fehlschläge entsprechen der
fehlenden Implementierung (Rollenkatalog, Zuweisung, TESTER-Fallback). Die
Bestandsschutz-Tests (unbekannte Rolle, Vibe-Regeln soweit ohne neue Rolle
prüfbar, expliziter TESTER, ohne Zustandsordner, REVIEWER-Fallback) waren
bereits grün.

Wörtliche Ausgabe:

```text
test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json)
Name: Alle vier neuen Rollen werden gespeichert. ... ERROR
test_new_roles_are_visible_in_the_agent_list (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_new_roles_are_visible_in_the_agent_list)
Name: Agentenliste zeigt die neuen Rollen. ... ERROR
test_new_roles_do_not_change_the_vibe_protection_rules (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_new_roles_do_not_change_the_vibe_protection_rules)
Name: Vibe-Schutzregeln gelten unverändert. ... ERROR
test_role_catalog_contains_existing_and_new_roles (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_role_catalog_contains_existing_and_new_roles)
Name: Rollenkatalog enthält alle vereinbarten Rollen. ... FAIL
test_unknown_role_is_rejected_without_changing_profiles_json (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_unknown_role_is_rejected_without_changing_profiles_json)
Name: Unbekannte Rolle wird abgelehnt, Datei bleibt unverändert. ... ok
test_cli_preflight_resolves_tester_from_state_directory (tests.unit.test_ap17_agent_roles.TesterRoleCliTest.test_cli_preflight_resolves_tester_from_state_directory)
Name: CLI-Preflight löst TESTER über --state auf. ... FAIL
test_cli_preflight_without_state_still_blocks_missing_tester (tests.unit.test_ap17_agent_roles.TesterRoleCliTest.test_cli_preflight_without_state_still_blocks_missing_tester)
Name: CLI-Preflight ohne --state meldet TESTER fehlt. ... ok
test_explicit_tester_argument_wins_over_the_tester_role (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_explicit_tester_argument_wins_over_the_tester_role)
Name: Ausdrücklicher TESTER hat Vorrang vor der Rolle. ... ok
test_missing_or_broken_profiles_file_blocks_with_tester_message (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_missing_or_broken_profiles_file_blocks_with_tester_message)
Name: Fehlende oder kaputte profiles.json blockiert ohne Absturz. ... ok
test_missing_tester_is_resolved_from_tester_role (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_missing_tester_is_resolved_from_tester_role)
Name: Fehlender TESTER wird aus der Rolle tester ergänzt. ... FAIL
test_project_env_tester_wins_over_the_tester_role (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_project_env_tester_wins_over_the_tester_role)
Name: TESTER aus project.env hat Vorrang vor der Rolle. ... ok
test_project_local_agent_file_satisfies_the_tester_role (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_project_local_agent_file_satisfies_the_tester_role)
Name: Projektlokaler Agent erfüllt die Tester-Rolle. ... FAIL
test_reviewer_fallback_still_resolves_from_profiles_json (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_reviewer_fallback_still_resolves_from_profiles_json)
Name: REVIEWER-Fallback bleibt unverändert. ... ok
test_stale_tester_role_entry_does_not_block_available_agent (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_stale_tester_role_entry_does_not_block_available_agent)
Name: Veralteter Rolleneintrag blockiert verfügbaren Tester nicht. ... FAIL
test_unavailable_explicit_tester_blocks_despite_a_valid_role (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_unavailable_explicit_tester_blocks_despite_a_valid_role)
Name: Nicht verfügbarer ausdrücklicher TESTER blockiert. ... ok
test_unavailable_tester_role_is_reported_with_its_name (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_unavailable_tester_role_is_reported_with_its_name)
Name: Nicht verfügbarer Rollen-Tester wird mit Namen gemeldet. ... FAIL
test_without_state_directory_missing_tester_still_blocks (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_without_state_directory_missing_tester_still_blocks)
Name: Ohne Zustandsordner bleibt der Befund TESTER fehlt. ... ok

======================================================================
ERROR: test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json)
Name: Alle vier neuen Rollen werden gespeichert.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 226, in test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json
    returned = self.cli.agent_role_set(agent_name(role), role)
  File "/tmp/opencode/vibe-ap17/bin/vibe", line 2842, in agent_role_set
    raise ValueError("Unbekannte Rolle: " + role)
ValueError: Unbekannte Rolle: tester

======================================================================
ERROR: test_new_roles_are_visible_in_the_agent_list (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_new_roles_are_visible_in_the_agent_list)
Name: Agentenliste zeigt die neuen Rollen.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 243, in test_new_roles_are_visible_in_the_agent_list
    self.cli.agent_role_set(agent_name(role), role)
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
  File "/tmp/opencode/vibe-ap17/bin/vibe", line 2842, in agent_role_set
    raise ValueError("Unbekannte Rolle: " + role)
ValueError: Unbekannte Rolle: tester

======================================================================
ERROR: test_new_roles_do_not_change_the_vibe_protection_rules (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_new_roles_do_not_change_the_vibe_protection_rules)
Name: Vibe-Schutzregeln gelten unverändert.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 292, in test_new_roles_do_not_change_the_vibe_protection_rules
    self.cli.agent_role_set("second", "analyst")
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^
  File "/tmp/opencode/vibe-ap17/bin/vibe", line 2842, in agent_role_set
    raise ValueError("Unbekannte Rolle: " + role)
ValueError: Unbekannte Rolle: analyst

======================================================================
FAIL: test_role_catalog_contains_existing_and_new_roles (tests.unit.test_ap17_agent_roles.RoleCatalogTest.test_role_catalog_contains_existing_and_new_roles)
Name: Rollenkatalog enthält alle vereinbarten Rollen.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 209, in test_role_catalog_contains_existing_and_new_roles
    self.assertEqual(
    ~~~~~~~~~~~~~~~~^
        set(roles), set(EXISTING_ROLES) | set(NEW_ROLES), roles
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
AssertionError: Items in the second set but not the first:
'tester'
'content-creator'
'analyst'
'sonstiges' : ('coder', 'reviewer', 'vibe')

======================================================================
FAIL: test_cli_preflight_resolves_tester_from_state_directory (tests.unit.test_ap17_agent_roles.TesterRoleCliTest.test_cli_preflight_resolves_tester_from_state_directory)
Name: CLI-Preflight löst TESTER über --state auf.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 616, in test_cli_preflight_resolves_tester_from_state_directory
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 2 != 0 : BLOCKIERT: TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.


======================================================================
FAIL: test_missing_tester_is_resolved_from_tester_role (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_missing_tester_is_resolved_from_tester_role)
Name: Fehlender TESTER wird aus der Rolle tester ergänzt.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 411, in test_missing_tester_is_resolved_from_tester_role
    self.assertEqual(errors, [])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^
AssertionError: Lists differ: ['TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.'] != []

First list contains 1 additional elements.
First extra element 0:
'TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.'

- ['TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.']
+ []

======================================================================
FAIL: test_project_local_agent_file_satisfies_the_tester_role (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_project_local_agent_file_satisfies_the_tester_role)
Name: Projektlokaler Agent erfüllt die Tester-Rolle.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 433, in test_project_local_agent_file_satisfies_the_tester_role
    self.assertEqual(errors, [])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^
AssertionError: Lists differ: ['TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.'] != []

First list contains 1 additional elements.
First extra element 0:
'TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.'

- ['TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.']
+ []

======================================================================
FAIL: test_stale_tester_role_entry_does_not_block_available_agent (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_stale_tester_role_entry_does_not_block_available_agent)
Name: Veralteter Rolleneintrag blockiert verfügbaren Tester nicht.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 454, in test_stale_tester_role_entry_does_not_block_available_agent
    self.assertEqual(errors, [])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^
AssertionError: Lists differ: ['TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.'] != []

First list contains 1 additional elements.
First extra element 0:
'TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.'

- ['TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.']
+ []

======================================================================
FAIL: test_unavailable_tester_role_is_reported_with_its_name (tests.unit.test_ap17_agent_roles.TesterRolePreflightTest.test_unavailable_tester_role_is_reported_with_its_name)
Name: Nicht verfügbarer Rollen-Tester wird mit Namen gemeldet.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/unit/test_ap17_agent_roles.py", line 472, in test_unavailable_tester_role_is_reported_with_its_name
    self.assertTrue(
    ~~~~~~~~~~~~~~~^
        any("veralteter-tester" in error for error in errors), errors
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
AssertionError: False is not true : ['TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.']

----------------------------------------------------------------------
Ran 17 tests in 0.278s

FAILED (failures=6, errors=3)
```

## Rotphase — Browser

Befehl (mit Browser-Pfad, siehe Umgebungs-Hinweis):

```
PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap17_agent_roles_ui -v
```

Ergebnis: 2 Tests, 1 Failure, 1 Error. Beide Fehlschläge entsprechen der
fehlenden UI-Implementierung: Die neuen Optionen fehlen, daher kann
`tester` nicht ausgewählt werden.

Wörtliche Ausgabe:

```text
test_01_role_select_offers_the_new_roles (tests.browser.test_ap17_agent_roles_ui.Ap17AgentRolesBrowserTest.test_01_role_select_offers_the_new_roles)
Name: Rollenauswahl bietet alle vier neuen Rollen an. ... FAIL
test_02_tester_role_is_saved_and_shown_after_reload (tests.browser.test_ap17_agent_roles_ui.Ap17AgentRolesBrowserTest.test_02_tester_role_is_saved_and_shown_after_reload)
Name: Auswahl tester wird gespeichert und nach Neuladen angezeigt. ... ERROR

======================================================================
ERROR: test_02_tester_role_is_saved_and_shown_after_reload (tests.browser.test_ap17_agent_roles_ui.Ap17AgentRolesBrowserTest.test_02_tester_role_is_saved_and_shown_after_reload)
Name: Auswahl tester wird gespeichert und nach Neuladen angezeigt.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/browser/test_ap17_agent_roles_ui.py", line 294, in test_02_tester_role_is_saved_and_shown_after_reload
    select.select_option("tester", timeout=5000)
    ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/nutzer/.local/lib/python3.14/site-packages/playwright/sync_api/_generated.py", line 20226, in select_option
    self._sync(
    ~~~~~~~~~~^
        self._impl_obj.select_option(
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<7 lines>...
        )
        ^
    )
    ^
  File "/home/nutzer/.local/lib/python3.14/site-packages/playwright/_impl/_sync_base.py", line 115, in _sync
    return task.result()
           ~~~~~~~~~~~^^
  File "/home/nutzer/.local/lib/python3.14/site-packages/playwright/_impl/_locator.py", line 637, in select_option
    return await self._frame.select_option(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
    )
    ^
  File "/home/nutzer/.local/lib/python3.14/site-packages/playwright/_impl/_frame.py", line 815, in select_option
    return await self._channel.send("selectOption", self._timeout, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/nutzer/.local/lib/python3.14/site-packages/playwright/_impl/_connection.py", line 76, in send
    return await self._connection.wrap_api_call(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
    )
    ^
  File "/home/nutzer/.local/lib/python3.14/site-packages/playwright/_impl/_connection.py", line 632, in wrap_api_call
    raise rewrite_error(error, f"{parsed_st['apiName']}: {error}") from None
playwright._impl._errors.TimeoutError: Locator.select_option: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("select[data-role=\"tester\"]")
    - locator resolved to <select data-role="tester" aria-label="Rolle von tester">…</select>
  - attempting select option action
    2 × waiting for element to be visible and enabled
      - did not find some options
    - retrying select option action
    - waiting 20ms
    2 × waiting for element to be visible and enabled
      - did not find some options
    - retrying select option action
      - waiting 100ms
    10 × waiting for element to be visible and enabled
       - did not find some options
     - retrying select option action
       - waiting 500ms


======================================================================
FAIL: test_01_role_select_offers_the_new_roles (tests.browser.test_ap17_agent_roles_ui.Ap17AgentRolesBrowserTest.test_01_role_select_offers_the_new_roles)
Name: Rollenauswahl bietet alle vier neuen Rollen an.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/opencode/vibe-ap17/tests/browser/test_ap17_agent_roles_ui.py", line 276, in test_01_role_select_offers_the_new_roles
    self.assertIn(role, values)
    ~~~~~~~~~~~~~^^^^^^^^^^^^^^
AssertionError: 'tester' not found in ['', 'coder', 'reviewer', 'vibe']

----------------------------------------------------------------------
Ran 2 tests in 6.041s

FAILED (failures=1, errors=1)
```

## Umgebung und Blocker

- Python: 3.14.8; Playwright ist unter
  `/home/nutzer/.local/lib/python3.14/site-packages/playwright` installiert.
- Erster Browser-Lauf ohne Anpassung schlug in `setUpClass` fehl, weil die
  Sandbox `XDG_CACHE_HOME=/tmp/opencode/vibe-sandbox/.../cache` setzt und
  Playwright dort keine Browser findet. Wörtliche Blocker-Meldung:

  ```text
  playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist at /tmp/opencode/vibe-sandbox/vibe-3cdc11f549/cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell
  ╔════════════════════════════════════════════════════════════╗
  ║ Looks like Playwright was just installed or updated.       ║
  ║ Please run the following command to download new browsers: ║
  ║                                                            ║
  ║     playwright install                                     ║
  ║                                                            ║
  ║ <3 Playwright Team                                         ║
  ╚════════════════════════════════════════════════════════════╝
  ```

- Die Browser liegen tatsächlich unter `/home/nutzer/.cache/ms-playwright`
  (`chromium-1243`, `chromium_headless_shell-1243`). Der zweite Lauf mit
  `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright` startete das echte
  Dashboard und Chromium erfolgreich; die oben dokumentierte Rotphase ist
  daher eine echte fachliche Rotphase, kein Infrastrukturblocker.
- Es wurden keine produktiven HOME-/VIBE-Konfigurationen verwendet. Unit-Tests
  arbeiten mit `tempfile.TemporaryDirectory`; der Browser-Test setzt VIBE, HOME,
  STATE, RUNTIME und AGENTS_DIR auf temporäre Pfade und verwendet ein
  Ersatz-`opencode`.
- Keine Modellaufrufe, keine OAuth-Anmeldungen, keine produktiven MCP-Aufrufe.
- Die Testdateien und dieser Bericht wurden nicht committet; Branch, Staging und
  Commits bleiben beim koordinierenden Coding-Agenten.

## Erwartung an die Implementierung (keine Vorgabe, nur Ableitung)

Damit die Rotphase grün wird, müssen die Tests aus AP17/SPEC erfüllt werden:
Rollenkatalog und Validierung um die vier neuen Rollen erweitern, die
Rollenoptionen im Dashboard ergänzen und den TESTER-Fallback im Preflight
analog zum bestehenden REVIEWER-Fallback über die Rolle `tester` auflösen.
Die Tests prüfen ausschließlich beobachtbares Verhalten (Rückgabewerte,
`profiles.json`, `agents_all`, Preflight-Befunde, UI-Auswahl), keine internen
Implementierungsdetails.

## Anonymisierung

- Datum: 2026-11-15
- Persönliche Home-Pfadanteile wurden in diesem Bericht durch die
  Repository-Konvention `/home/nutzer/...` ersetzt.
- Der Nachweiswert bleibt unverändert: Die Rotphase wurde mit dem dokumentierten
  Befehl über die Umgebungsvariable `PLAYWRIGHT_BROWSERS_PATH` ausgeführt; nur
  der persönliche Pfadanteil wurde anonymisiert.

## Nachträge (Review Runde 1, 2026-11-15)

Herkunft beider Änderungen: Test-Agent. Es handelt sich ausschließlich um
Teständerungen (Bestandstests angepasst bzw. Isolation nachgeschärft); die
Produktionsdateien wurden dabei nicht verändert. Beide Nachträge wurden nach der
Rotphase und nach Vorliegen des Reviews ausgeführt und erneut tatsächlich
ausgeführt.

### Nachtrag 1 — Isolationsparität im AP17-Browser-Test

Bezug: Reviewbefund 4 (Minor), `docs/reviews/AP17-review-1.md` — ererbte
`AGENT`-Umgebungsvariable wurde im Browser-Test nicht isoliert, während der
Unit-Test sie bereits entfernt.

- Datei: `tests/browser/test_ap17_agent_roles_ui.py`
- Änderung: `"AGENT"` wurde in die Liste `ISOLATED_ENV` aufgenommen (letzter
  Eintrag). `isolated_env` entfernt damit vor dem Start des echten Dashboards
  einen geerbten `AGENT`-Wert aus der Prozessumgebung; der im Test gesetzte Wert
  bleibt weiterhin ausschließlich in `project.env` bzw. in den expliziten
  `env.update`-Werten. Es wurde kein erwartetes Verhalten abgeschwächt, keine
  Assertion entfernt und kein Testfall gelöscht.
- Testfall: **`test_02_tester_role_is_saved_and_shown_after_reload`**
  - Vorbedingung: Die aufrufende Shell exportiert `AGENT` mit einem beliebigen
    Wert; das Dashboard läuft auf eigenem Port und eigener Isolation.
  - Aktion: Der Test startet das Dashboard und liest bzw. schreibt die
    Rollenzuweisung über die UI; anschließend wird `profiles.json` geprüft.
  - Erwartetes Ergebnis: Der geerbte `AGENT`-Wert wirkt sich nicht aus; die
    Zuweisung `tester` wird gespeichert und nach dem Neuladen angezeigt, ohne
    Beeinflussung durch die umgebende Umgebung. Der Test bleibt auch ohne
    gesetztes `AGENT` in der Shell unverändert grün.

Nachlauf (tatsächlich ausgeführt):

```
PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap17_agent_roles_ui -v
```

Ergebnis: 2 Tests, OK. Zusätzlich als Regressionsschutz der Unit-Ebene:

```
python3 -m unittest tests.unit.test_ap17_agent_roles -v
```

Ergebnis: 17 Tests, OK.

### Nachtrag 2 — Katalogerwartung des AP03-Browsertests

Bezug: AP17 erweitert den Rollenkatalog (Ticket). Der Bestandstest aus AP03
prüfte die Rollenoptionen mit exakter Mengengleichheit gegen den Katalog
**vor** AP17 und wurde dadurch zur einzigen fachlichen AP17-Abweichung im
Vollsuite-Fehlersatzabgleich gegen Baseline `35233ff`.

- Datei: `tests/browser/test_ap03_agents_ui.py`, Klasse
  `Ap03AgentsBrowserTest`, `test_02_role_change_updates_profiles_json_and_is_shown`
  (Optionen-Auslesung des `select[data-role="tester"]`, Zeilen um 365).
- Änderung: Die Erwartung wurde von `["", "coder", "reviewer", "vibe"]` auf den
  durch AP17 erweiterten Katalog
  `["", "coder", "reviewer", "vibe", "tester", "analyst", "sonstiges", "content-creator"]`
  aktualisiert. Die Prüfung erfolgt weiterhin als exakte Mengengleichheit
  (`assertEqual(sorted(values), sorted([...]))`) — keine Abschwächung auf
  `assertIn`, keine Toleranz für zusätzliche oder fehlende Optionen. Der
  anschließende Rollenwechsel (`coder`) und die Prüfung von `profiles.json`
  blieben unverändert.
- Testfall: **`test_02_role_change_updates_profiles_json_and_is_shown`**
  - Vorbedingung: Das echte Dashboard läuft auf eigenem Port; die Agentenliste
    enthält den Agenten `tester`; es gelten die AP17-Rollen.
  - Aktion: Die Optionen von `select[data-role="tester"]` werden ausgelesen;
    danach wird `coder` gewählt und `profiles.json` geprüft.
  - Erwartetes Ergebnis: Die Optionswerte entsprechen exakt dem um die vier
    AP17-Rollen erweiterten Katalog (Reihenfolge irrelevant, Menge exakt). Der
    Rollenwechsel wird in `profiles.json` gespeichert und in der Liste angezeigt.

Nachlauf (tatsächlich ausgeführt):

```
PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap03_agents_ui -v
```

Ergebnis: 6 Tests, OK.

### Zusammenfassung der Nachläufe

| Befehl | Ergebnis |
| --- | --- |
| `python3 -m unittest tests.unit.test_ap17_agent_roles -v` | 17 Tests, OK |
| `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap17_agent_roles_ui -v` | 2 Tests, OK |
| `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap03_agents_ui -v` | 6 Tests, OK |

- Beide Nachträge sind Teständerungen des Test-Agenten; es gab keine
  Implementierungsänderung und keine Abschwächung bestehender Zusicherungen.
- Persönliche Pfadanteile sind wie im übrigen Bericht durch die Konvention
  `/home/nutzer/...` ersetzt; der Nachweiswert der Befehle bleibt unverändert.
- Es wurde nichts committet; Branch, Staging und Commit bleiben beim
  koordinierenden Coding-Agenten.
