# GH-114 — independent test report (test-first, start commit 9d72dc6)

Scope: four acceptance criteria of "cost overview ui improvements". Only the
browser test file was changed; no production code, manifest or feature docs.

## Where the tests live

`tests/browser/test_activity_ui.py`, new class
`CostsOverviewUiTest(F34ActivityEvalsBrowserTest)` (inserted after `CostsTest`).
It reuses the existing isolated fixture (temporary VIBE root, temporary HOME,
dedicated ports, local Chromium) and the helpers `open_evaluations`, `wait_until`,
`post_json`, `assert_clean_page`. It deliberately does **not** inherit
`CostsTest`, otherwise the existing cost tests would run twice in one shared
fixture and contaminate each other through saved prices/language changes.

New methods (one per behaviour, feature-oriented names):

1. `test_project_rows_stay_single_line_with_long_name_at_1400_and_900px`
2. `test_monthly_summary_de_is_labeled_locale_formatted_and_compact`
3. `test_monthly_summary_en_us_uses_english_locale_number_format`
4. `test_price_editor_lists_each_used_model_once_with_subagent_roles`
5. `test_cost_entry_accepts_locale_currency_values_and_rejects_invalid`
6. `test_saving_unmodified_usd_price_keeps_stored_eur_value` (additional
   regression case for the confirmed price-drift defect; see final section)
7. `test_german_thousands_separator_price_is_saved_as_full_value`
8. `test_english_thousands_separator_price_is_saved_as_full_value`

Cases 7–8 cover the review blocker for grouped thousands separators.

Existing tests were not edited or weakened.

## Hooks / selectors requested from the implementation

These are tester-chosen hooks for the coder; they are deliberately small and
can be adjusted after coordination with me.

| Criterion | Selector / hook | Required behaviour |
| --- | --- | --- |
| 1 | `tr[data-nv-cost-project="<name>"]` (existing) | exactly one row per project; detail rows keep their separate `data-nv-cost-detail` hook |
| 1 | `[data-nv-cost-name]` inside the project row | carries the full project name in `title`; computed `white-space: nowrap`, `overflow: hidden|clip`, `text-overflow: ellipsis`; row and all `td` heights `<= 44px` at 1400px and 900px |
| 1 | `.nv-table-wrap` (existing) and `table[data-nv-cost-projects] th` | wrapper has `overflow-x: auto|scroll`; all 7 headers remain present (horizontal scrolling allowed) |
| 2 | `div[data-nv-cost-month="<month>"]` (existing, must stay) | month label `2026-11` visible in the element |
| 2 | `[data-nv-cost-month-field="sessions\|input\|cached\|output\|cost"]` inside it | exactly one element per field, each with label and formatted value; five fields in total |
| 3 | `section[data-nv-price-editor]` (existing) | editor as before |
| 3 | `[data-nv-price-row="<model-id>"]` | exactly one row per model used in the project (usage + `/api/project-agents?name=<project>`), with three `input[data-nv-price-field]` each |
| 3 | `[data-nv-price-agent]` inside the model row | one visible badge per agent/role, e.g. `coding-agent`, `general`, `explore` |
| 3 | `input[data-nv-price-model][data-nv-price-field]` (existing) | existing prices are pre-filled and editable |
| 4 | `input[data-nv-price-model][data-nv-price-field]` | must accept locale-formatted currency text (`1,50 €`) as well as plain `1.5`; negative / invalid / empty values show `[data-nv-eval-error]` (existing hook) and must not POST/save |
| 4 | `button[data-nv-action='cost-prices-save']`, `[data-nv-toast-auto]` (existing) | save flow unchanged |

Stubs: `page.route("**/api/costs*", ...)` (GET by `name=`, POST captured), and
`page.route("**/api/project-agents*", ...)` returning
`{agents: [{name, effective_model, opencode}, ...]}`. No real model calls; all
state is inside the fixture's temporary directory.

## Red run on the clean start commit

Command (repo root, Playwright/Chromium 1255 and Python 3.14 available):

```
python3 -m py_compile tests/browser/test_activity_ui.py   # syntax OK
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest -v
```

Observed: `Ran 5 tests in 89.046s` → `FAILED (failures=13, errors=4)`, exit 1.
Exact failure messages:

```
test_cost_entry_accepts_locale_currency_values_and_rejects_invalid ...
  (invalid='abc') ... ERROR
playwright._impl._errors.Error: Locator.fill: Error: Cannot type text into input[type=number]
  - locator resolved to <input min="0" type="number" step="0.0001"
    data-nv-price-field="input" aria-label="Eingabe opencode/model-a"
    data-nv-price-model="opencode/model-a"/>
  - fill("abc")
...
test_cost_entry_accepts_locale_currency_values_and_rejects_invalid ... ERROR
playwright._impl._errors.Error: Locator.fill: Error: Cannot type text into input[type=number]
  - fill("1,50 €")
```

```
test_monthly_summary_de_is_labeled_locale_formatted_and_compact ...
  (field='sessions') ... AssertionError: 1 != 0 : Feld sessions fehlt oder ist mehrfach vorhanden
  (field='input')    ... AssertionError: 1 != 0 : Feld input fehlt oder ist mehrfach vorhanden
  (field='cached')   ... AssertionError: 1 != 0 : Feld cached fehlt oder ist mehrfach vorhanden
  (field='output')   ... AssertionError: 1 != 0 : Feld output fehlt oder ist mehrfach vorhanden
  (field='cost')     ... AssertionError: 1 != 0 : Feld cost fehlt oder ist mehrfach vorhanden
playwright._impl._errors.TimeoutError: Locator.inner_text: Timeout 30000ms exceeded.
  - waiting for locator("div[data-nv-cost-month=\"2026-11\"]").first
    .locator("[data-nv-cost-month-field=\"cost\"]").first
```

Same five subtest failures plus the same timeout for the `en-US` test.

```
test_price_editor_lists_each_used_model_once_with_subagent_roles ...
AssertionError: Der Editor zeigt nicht genau die drei verwendeten Modelle
```

```
test_project_rows_stay_single_line_with_long_name_at_1400_and_900px ...
  (viewport=1400) ... AssertionError: 1 != 0 : Namens-Hook [data-nv-cost-name] fehlt
  (viewport=900)  ... AssertionError: 1 != 0 : Namens-Hook [data-nv-cost-name] fehlt
```

All failures are at the new assertions for the intended reasons. Contract parts
that were already green before the hook checks: one `tr[data-nv-cost-project]`
per project, all 7 headers present, `.nv-table-wrap` scrollable, existing
`div[data-nv-cost-month]` found and visible, price link and editor visible,
negative and empty price inputs already produce `[data-nv-eval-error]` without a
POST. These are implicit contract evidence, not new tests.

## Baseline: all three red `CostsTest` cases pre-date GH-114

The coder reported three red cases in `CostsTest`. Each was reproduced on a
clean control copy of the start commit (full repository exported with
`git archive 9d72dc6c33a595b5e26c99dcdc435302e558ca19 | tar -x -C <temp>`;
the copy is outside the package worktree). Each case was run both singly and as
part of the complete class; results were identical:

```
# control copy, git archive of 9d72dc6
python3 -m unittest tests.browser.test_activity_ui.CostsTest -v
Ran 6 tests in 51.574s
FAILED (failures=2, errors=1)

AssertionError: Der fehlende Preis meldet sich nicht in der Detail-Tabelle
  -> test_costs_missing_price_editor_save_updates
AssertionError: '1000000' != '0'
  -> test_costs_summary_statistics_and_currency_eur
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 20000ms exceeded.
  waiting for locator("[data-nv-costs-empty]").first to be visible
  -> test_costs_empty_state_without_database
```

The same class on the final GH-114 worktree:

```
python3 -m unittest tests.browser.test_activity_ui.CostsTest -v
Ran 6 tests in 50.808s
FAILED (failures=2, errors=1)

AssertionError: Der fehlende Preis meldet sich nicht in der Detail-Tabelle
AssertionError: '1000000' != '0'
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 20000ms exceeded.
  waiting for locator("[data-nv-costs-empty]").first to be visible
```

Normalized diff of the two result summaries (excluding durations): **no
difference**. All three are therefore `BASELINE-OK`, not regressions of
GH-114. Root cause of the first two: since GH-99 the overview/detail is built
from persisted package usage, but the F34 fixture only inserts a live
`opencode.db` session and no persisted package usage, so no "Preis fehlt" badge
and no 1 Mio. token stats appear. The empty-state case likewise never sees
`overview.available === false` with that fixture. No existing test was changed
or weakened; the new GH-114/4 case uses a stateful `/api/costs` stub (GET +
POST) to avoid that fixture gap while still testing the parser contract.

## Official green run (final implementation)

```
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest -v
```

Exact output:

```
test_cost_entry_accepts_locale_currency_values_and_rejects_invalid (tests.browser.test_activity_ui.CostsOverviewUiTest.test_cost_entry_accepts_locale_currency_values_and_rejects_invalid)
GH-114/4: Währungseingabe, Validierung und Übernahme in der Ansicht. ... ok
test_monthly_summary_de_is_labeled_locale_formatted_and_compact (tests.browser.test_activity_ui.CostsOverviewUiTest.test_monthly_summary_de_is_labeled_locale_formatted_and_compact)
GH-114/2: strukturierte deutsche Monatssummary ohne Überlauf. ... ok
test_monthly_summary_en_us_uses_english_locale_number_format (tests.browser.test_activity_ui.CostsOverviewUiTest.test_monthly_summary_en_us_uses_english_locale_number_format)
GH-114/2: Monatssummary folgt der aktiven Sprache (en-US). ... ok
test_price_editor_lists_each_used_model_once_with_subagent_roles (tests.browser.test_activity_ui.CostsOverviewUiTest.test_price_editor_lists_each_used_model_once_with_subagent_roles)
GH-114/3: Hauptagent, Subagenten und Duplikatverarbeitung. ... ok
test_project_rows_stay_single_line_with_long_name_at_1400_and_900px (tests.browser.test_activity_ui.CostsOverviewUiTest.test_project_rows_stay_single_line_with_long_name_at_1400_and_900px)
GH-114/1: ein Projekt = eine Zeile, langer Name gekürzt mit Tooltip. ... ok

----------------------------------------------------------------------
Ran 5 tests in 5.512s

OK
```

Exit code 0. All four acceptance criteria are now covered green; the two
locale cases prove `de-DE`/`en-US` number and currency formatting, and the
currency-field case proves the parser still accepts plain `1.5` syntax through
the unchanged `CostsTest` contract (which remains baseline-red for the fixture
reason above).

## Test-file integrity

`git diff 9d72dc6 -- tests/browser/test_activity_ui.py` contains **only
additions** (703 lines for `CostsOverviewUiTest`); the only removed line is the
diff header itself. Hashes over time: original five-test run
`d2f0051ef8cfe29d10114e13522111bc4018baa31005b3a19059f715e6d7fb3e`, after the
USD-drift case `368ef7b9265dfc8bfecd7d15539a133c132dacd0a271ed3c294247f561eec02a`,
after the two grouping cases
`f7d647d62ee74f7847b79dc3c73c3563c42318de41fe4dc08aef801ecbfbb6b0`, and after
hardening the helper's rebuild wait
`dbc49fe75f1bba7cf09b14b8a968c26f66a460b682dc1593a10d670ee78cec4a`.
Method list and line range now: 1717–2417, eight test methods. The five
original methods and the drift case remained byte-identical; only the helper
`assert_price_inputs_saved_as` and the two new methods were appended. No
production file
was changed by the tester: production edits in the worktree
(`bin/web/nova-evals.js`, `bin/web/nova.css`, `docs/import-manifest.json`, and
the coordinator/coder feature docs) came from the implementation side.

## Checks performed and remaining scope

```
python3 -m py_compile tests/browser/test_activity_ui.py
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest -v
python3 -m unittest tests.browser.test_activity_ui.CostsTest -v
bash scripts/verify.sh quick
```

`verify.sh quick`: exit 0 (import manifest for 70 files, 149 Python / 8 Bash /
5 JSON syntax checks, no secrets). Package/full runs and independent review
remain with the coordinator. After the drift fix below, no coverage gap
remains for the four GH-114 criteria; the only other open item is the
pre-existing F34 fixture debt documented above.

## Additional regression case: USD price drift (RED → GREEN)

Confirmed defect: `nvEvalPriceInput()` renders an EUR price with the USD rate
and at most four decimals, while `savePrices()` divides the parsed display
value by the rate again. With `usd_rate = 1.19`, a stored EUR price of `0.1234`
is displayed as `0,1468` and saved back as `0.1233613445…`.

New case: `CostsOverviewUiTest.test_saving_unmodified_usd_price_keeps_stored_eur_value`.
Setup: `POST /api/ui_settings {currency: USD, usd_rate: 1.19}`, stateful
`/api/costs` stub with `user_prices = {input: 0.1234, cached_input: 0, output: 0}`,
editor opened via the project price link. Action: click `cost-prices-save`
twice without touching the fields. Expectation: exactly two POSTs, each with
`prices[model]["input"]` equal to 0.1234 (`assertAlmostEqual(places=6)`), no
visible `[data-nv-eval-error]`, no JavaScript errors. Settings are reset to
EUR/1.0 in a `finally` block.

Command and exact red output on the implementation before the fix:

```
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest.test_saving_unmodified_usd_price_keeps_stored_eur_value -v
```

```
test_saving_unmodified_usd_price_keeps_stored_eur_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_saving_unmodified_usd_price_keeps_stored_eur_value)
GH-114/4: Speichern ohne Änderung darf EUR-Preis nicht verschieben. ... FAIL

======================================================================
FAIL: test_saving_unmodified_usd_price_keeps_stored_eur_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_saving_unmodified_usd_price_keeps_stored_eur_value)
GH-114/4: Speichern ohne Änderung darf EUR-Preis nicht verschieben.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<package-worktree>/tests/browser/test_activity_ui.py", line 2286, in test_saving_unmodified_usd_price_keeps_stored_eur_value
    self.assertAlmostEqual(
    ~~~~~~~~~~~~~~~~~~~~~~^
        0.1234, state["posts"][-1]["prices"][model]["input"],
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        places=6,
        ^^^^^^^^^
        msg="EUR-Preis driftet nach ungeändertem Speichern: "
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        + repr(state["posts"][-1]["prices"][model]))
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 0.1234 != 0.12336134453781514 within 6 places (3.865546218485838e-05 difference) : EUR-Preis driftet nach ungeändertem Speichern: {'input': 0.12336134453781514, 'cached_input': 0, 'output': 0}

----------------------------------------------------------------------
Ran 1 test in 3.081s

FAILED (failures=1)
```

Exit 1. The first POST happened exactly once and no error box appeared before
the value assertion; only the stored EUR value is wrong. This is a valid
red-first proof of the defect.

After the coder's fix in `bin/web/nova-evals.js`, the same single case turns
green with the unchanged test (no test edit after the red run; test-file
SHA-256 is still
`368ef7b9265dfc8bfecd7d15539a133c132dacd0a271ed3c294247f561eec02a`).
The value assertion, the two-POST check, the error-box check and
`assert_clean_page()` all pass.

## Official final green run (six tests, after the drift fix)

```
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest -v
```

Exact output (exit code 0):

```
test_cost_entry_accepts_locale_currency_values_and_rejects_invalid (tests.browser.test_activity_ui.CostsOverviewUiTest.test_cost_entry_accepts_locale_currency_values_and_rejects_invalid)
GH-114/4: Währungseingabe, Validierung und Übernahme in der Ansicht. ... ok
test_monthly_summary_de_is_labeled_locale_formatted_and_compact (tests.browser.test_activity_ui.CostsOverviewUiTest.test_monthly_summary_de_is_labeled_locale_formatted_and_compact)
GH-114/2: strukturierte deutsche Monatssummary ohne Überlauf. ... ok
test_monthly_summary_en_us_uses_english_locale_number_format (tests.browser.test_activity_ui.CostsOverviewUiTest.test_monthly_summary_en_us_uses_english_locale_number_format)
GH-114/2: Monatssummary folgt der aktiven Sprache (en-US). ... ok
test_price_editor_lists_each_used_model_once_with_subagent_roles (tests.browser.test_activity_ui.CostsOverviewUiTest.test_price_editor_lists_each_used_model_once_with_subagent_roles)
GH-114/3: Hauptagent, Subagenten und Duplikatverarbeitung. ... ok
test_project_rows_stay_single_line_with_long_name_at_1400_and_900px (tests.browser.test_activity_ui.CostsOverviewUiTest.test_project_rows_stay_single_line_with_long_name_at_1400_and_900px)
GH-114/1: ein Projekt = eine Zeile, langer Name gekürzt mit Tooltip. ... ok
test_saving_unmodified_usd_price_keeps_stored_eur_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_saving_unmodified_usd_price_keeps_stored_eur_value)
GH-114/4: Speichern ohne Änderung darf EUR-Preis nicht verschieben. ... ok

----------------------------------------------------------------------
Ran 6 tests in 14.433s

OK
```

## Final baseline confirmation

```
python3 -m unittest tests.browser.test_activity_ui.CostsTest -v
```

```
Ran 6 tests in 52.112s
FAILED (failures=2, errors=1)
```

Exactly the three baseline cases from the `git archive` control copy of
9d72dc6, with identical failure messages and source lines:

```
ERROR: test_costs_empty_state_without_database
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 20000ms exceeded.
  waiting for locator("[data-nv-costs-empty]").first to be visible
FAIL: test_costs_missing_price_editor_save_updates
AssertionError: Der fehlende Preis meldet sich nicht in der Detail-Tabelle
FAIL: test_costs_summary_statistics_and_currency_eur
AssertionError: '1000000' != '0'
```

A normalized comparison (durations removed) of the control-copy result and
this final result is identical: no new failures, no weakened assertions. The
three passing `CostsTest` cases (`currency_usd`, `project_table_expand`,
`show_persisted_package_aggregation`) remain green. Baseline classification:
`BASELINE-OK` for all three.

## Final integrity statement

`git diff 9d72dc6 -- tests/browser/test_activity_ui.py` is purely additive
(703 lines; no removed test line except the diff header). No assertion was
deleted, relaxed or reordered.
No production file was edited by the tester; all production changes in the
worktree belong to the coder/coordinator. The report itself is the only other
file changed by me.

## Review blocker: grouped thousands separators (RED, awaiting fix)

`nvEvalParsePrice()` treats a lone separator as a decimal separator regardless
of locale. With de-DE, `1.234 €` is saved as `1.234` instead of `1234`; with
en-US, `1,234 €` suffers the same error. A plain one-decimal value such as
`1.5` must keep parsing as `1.5` — the de case includes it as a second POST so
that the fix cannot regress the plain syntax (the only existing test with
`1.5`, `CostsTest.test_costs_missing_price_editor_save_updates`, is baseline-red
for the unrelated F34 fixture reason documented above, so this new subtest is
the green proof of that contract).

New methods: `test_german_thousands_separator_price_is_saved_as_full_value`
and `test_english_thousands_separator_price_is_saved_as_full_value`, both using
the stateful `/api/costs` stub (GET detail/overview, POST captured), EUR/1.0,
and an editor opened via the project price link. The English case switches the
language with `POST /api/language {language: en}` and resets it to `de` in a
`finally` block. Both assert `assertAlmostEqual(1234, …, places=6)`, a hidden
`[data-nv-eval-error]` and `assert_clean_page()`.

Command and exact red output on the current (unfixed) implementation (paths
neutralized so the release content check stays clean):

```
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest.test_german_thousands_separator_price_is_saved_as_full_value tests.browser.test_activity_ui.CostsOverviewUiTest.test_english_thousands_separator_price_is_saved_as_full_value -v
```

```
test_german_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_german_thousands_separator_price_is_saved_as_full_value)
GH-114/4: de-DE ``1.234 €`` ist 1234, ``1.5`` bleibt 1.5. ...
  test_german_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_german_thousands_separator_price_is_saved_as_full_value) (raw='1.234 €', expected=1234)
GH-114/4: de-DE ``1.234 €`` ist 1234, ``1.5`` bleibt 1.5. ... FAIL
test_english_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_english_thousands_separator_price_is_saved_as_full_value)
GH-114/4: en-US ``1,234 €`` ist 1234. ...
  test_english_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_english_thousands_separator_price_is_saved_as_full_value) (raw='1,234 €', expected=1234)
GH-114/4: en-US ``1,234 €`` ist 1234. ... FAIL

======================================================================
FAIL: test_german_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_german_thousands_separator_price_is_saved_as_full_value) (raw='1.234 €', expected=1234)
GH-114/4: de-DE ``1.234 €`` ist 1234, ``1.5`` bleibt 1.5.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<package-worktree>/tests/browser/test_activity_ui.py", line 2374, in assert_price_inputs_saved_as
    self.assertAlmostEqual(
    ~~~~~~~~~~~~~~~~~~~~~~^
        expected, state["posts"][-1]["prices"][model]["input"],
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        places=6,
        ^^^^^^^^^
        msg="Falsch geparst: " + repr(raw) + " -> "
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        + repr(state["posts"][-1]["prices"][model]))
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 1234 != 1.234 within 6 places (1232.766 difference) : Falsch geparst: '1.234 €' -> {'input': 1.234, 'cached_input': 0, 'output': 0}

======================================================================
FAIL: test_english_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_english_thousands_separator_price_is_saved_as_full_value) (raw='1,234 €', expected=1234)
GH-114/4: en-US ``1,234 €`` ist 1234.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<package-worktree>/tests/browser/test_activity_ui.py", line 2374, in assert_price_inputs_saved_as
    self.assertAlmostEqual(
    ~~~~~~~~~~~~~~~~~~~~~~^
        expected, state["posts"][-1]["prices"][model]["input"],
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        places=6,
        ^^^^^^^^^
        msg="Falsch geparst: " + repr(raw) + " -> "
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        + repr(state["posts"][-1]["prices"][model]))
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 1234 != 1.234 within 6 places (1232.766 difference) : Falsch geparst: '1,234 €' -> {'input': 1.234, 'cached_input': 0, 'output': 0}

----------------------------------------------------------------------
Ran 2 tests in 5.704s

FAILED (failures=2)
```

Exit 1. In both cases exactly one POST happened and no error box appeared;
only the parsed value is wrong. The second de subtest (`1.5` → `1.5`) was not
reached because the first subtest already failed; it was verified in the green
run below. The coder then corrected `nvEvalParsePrice()` in
`bin/web/nova-evals.js` (locale-aware thousands separators).

## Final green proof for the grouping cases and full class

Both new cases pass with the unchanged assertions after the fix. An isolated
run first exposed a test-helper timing gap (the second fill happened before the
editor was redrawn after the first POST, so it saved the old value again); the
helper was hardened with a wait for the input to reflect the stub's new price.
No assertion was relaxed. Exact isolated output after hardening (exit 0):

```
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest.test_german_thousands_separator_price_is_saved_as_full_value tests.browser.test_activity_ui.CostsOverviewUiTest.test_english_thousands_separator_price_is_saved_as_full_value -v
```

```
test_german_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_german_thousands_separator_price_is_saved_as_full_value)
GH-114/4: de-DE ``1.234 €`` ist 1234, ``1.5`` bleibt 1.5. ... ok
test_english_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_english_thousands_separator_price_is_saved_as_full_value)
GH-114/4: en-US ``1,234 €`` ist 1234. ... ok

----------------------------------------------------------------------
Ran 2 tests in 9.330s

OK
```

The official final class run (all eight methods):

```
python3 -m unittest tests.browser.test_activity_ui.CostsOverviewUiTest -v
```

Exact output (exit code 0):

```
test_cost_entry_accepts_locale_currency_values_and_rejects_invalid (tests.browser.test_activity_ui.CostsOverviewUiTest.test_cost_entry_accepts_locale_currency_values_and_rejects_invalid)
GH-114/4: Währungseingabe, Validierung und Übernahme in der Ansicht. ... ok
test_english_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_english_thousands_separator_price_is_saved_as_full_value)
GH-114/4: en-US ``1,234 €`` ist 1234. ... ok
test_german_thousands_separator_price_is_saved_as_full_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_german_thousands_separator_price_is_saved_as_full_value)
GH-114/4: de-DE ``1.234 €`` ist 1234, ``1.5`` bleibt 1.5. ... ok
test_monthly_summary_de_is_labeled_locale_formatted_and_compact (tests.browser.test_activity_ui.CostsOverviewUiTest.test_monthly_summary_de_is_labeled_locale_formatted_and_compact)
GH-114/2: strukturierte deutsche Monatssummary ohne Überlauf. ... ok
test_monthly_summary_en_us_uses_english_locale_number_format (tests.browser.test_activity_ui.CostsOverviewUiTest.test_monthly_summary_en_us_uses_english_locale_number_format)
GH-114/2: Monatssummary folgt der aktiven Sprache (en-US). ... ok
test_price_editor_lists_each_used_model_once_with_subagent_roles (tests.browser.test_activity_ui.CostsOverviewUiTest.test_price_editor_lists_each_used_model_once_with_subagent_roles)
GH-114/3: Hauptagent, Subagenten und Duplikatverarbeitung. ... ok
test_project_rows_stay_single_line_with_long_name_at_1400_and_900px (tests.browser.test_activity_ui.CostsOverviewUiTest.test_project_rows_stay_single_line_with_long_name_at_1400_and_900px)
GH-114/1: ein Projekt = eine Zeile, langer Name gekürzt mit Tooltip. ... ok
test_saving_unmodified_usd_price_keeps_stored_eur_value (tests.browser.test_activity_ui.CostsOverviewUiTest.test_saving_unmodified_usd_price_keeps_stored_eur_value)
GH-114/4: Speichern ohne Änderung darf EUR-Preis nicht verschieben. ... ok

----------------------------------------------------------------------
Ran 8 tests in 22.077s

OK
```

The `1.5` → `1.5` subtest passed in these runs, so the thousands-separator fix
did not regress the plain decimal syntax. Final test-file SHA-256:
`dbc49fe75f1bba7cf09b14b8a968c26f66a460b682dc1593a10d670ee78cec4a`.
`git diff 9d72dc6 -- tests/browser/test_activity_ui.py` remains purely
additive (703 inserted lines, no removed assertions); no existing test was
weakened. A scan of this report finds no absolute home path, so the release
content check finding for `docs/reviews/GH-114-test-report.md` is resolved.
