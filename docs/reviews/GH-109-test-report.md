# GH-109 — Independent tester report (test-first phase)

- Ticket: GH-109 „Agents UI ANpassungen“ (`TICKET-GH-109.json`)
- Worktree: `vibe-GH-109-8JjBUi`, branch `feature/m0p/gh-109`, base HEAD `8997d4d1d5beb1ebcc8806cf23d3ebc2c4ba0e02`
- Role: independent tester; **only test files and this report were changed**. No production code was edited by me.
- Date: 2026-11-26

## Isolation and runner conventions

All browser cases use the existing `Ap22AgentsBrowserTest` / `AgentsBrowserTest`
harness in `tests/browser/test_agents_ui.py`. Each class creates its own
`tempfile.TemporaryDirectory` for `VIBE`, `HOME`, `VIBE_STATE`, `VIBE_RUNTIME`
and its own free loopback port via `free_port()`; no personal project, no
running installation, no real model calls and no production MCP calls are
touched. The unit case uses `tests/unit/test_agent_management.py`'s
`isolated_env()` fixture. Commands are run from the repository root.

## Important timing note

While I was writing the cases, a coder began editing `bin/web/nova-agents.js`
**in the same worktree**. To obtain honest red-phase evidence against the
untouched baseline, I ran the identical cases from an isolated copy created
with `git archive HEAD | tar -x -C <sandbox>` and copied **only my two modified
test files** into it. Production code in the assigned worktree was never
modified or reverted by me. The pristine run is the authoritative red phase;
the in-worktree run reflects the coder's partially landed changes.

## Added cases

| # | Case (file:line) | Requirement |
|---|---|---|
| 1 | `tests/browser/test_agents_ui.py:1662` `ListTest.test_header_search_and_new_agent_share_a_vertical_center` | 1 — header: common vertical centre + balanced gaps |
| 2 | `tests/browser/test_agents_ui.py:1708` `ListTest.test_agent_card_action_buttons_are_bottom_aligned_across_cards` | 2 — card buttons bottom-aligned at the same height on every card |
| 3 | `tests/browser/test_agents_ui.py:2150` `StructuredEditorTest.test_restore_selects_an_older_backup_and_restores_that_version` | 3 — a *chosen* backup (not just the newest) is restored |
| 4 | `tests/browser/test_agents_ui.py:2357` `AssignmentTest.test_assignment_checkbox_has_an_explicit_assign_label` | 4 — checkbox has an explicit accessible `Assign`/`Zugewiesen` name |
| 5 | `tests/browser/test_agents_ui.py:2391` / `:2404` `AssignmentLayoutTest.test_each_project_renders_exactly_one_assignment_row_with_visible_name` | 4 — exactly one row per project, visible project name, checkbox and model control in that row |
| 6 | `tests/unit/test_agent_management.py:486` `RestoreTest.test_restore_uses_an_explicitly_chosen_older_backup` | 3 — backend contract for an explicitly chosen older backup (already supported by backend) |

Supporting helper added: `ListTest._vertical_center` (`:1657`),
`StructuredEditorTest._backup_option_index` (`:2135`), and `import re` in the
top import block of `tests/browser/test_agents_ui.py` (line 9).

### 1. Header alignment

- Precondition: `#/agents` rendered with search input, page title and
  `agent-new` button.
- Action: measure bounding boxes of `input[data-nv-agent-search]`,
  `.nv-toolbar h2.nv-page-title`, `[data-nv-action='agent-new']` and
  `[data-nv-search]`.
- Expected: the three vertical centres agree within 4 px; the horizontal gap
  title→search equals the gap search→button within 4 px; no JS errors.
- Red (pristine HEAD):
  `AssertionError: 8.0 not less than or equal to 4 : Suchleiste und 'Neuer Agent' sind nicht vertikal ausgerichtet: Suche-Mitte 111.0, Knopf-Mitte 119.0`.
  Measured geometry: search centre 111, title centre 113, button centre 119 —
  the toolbar uses `align-items:center` but the enhanced search wrapper sits
  8 px above the button.

### 2. Agent card button alignment

- Precondition: at least two cards with different content heights (fixture
  contains five cards, `vibe-agent` has an extra chip).
- Action: measure each card and its `agent-edit` / `agent-delete` buttons.
- Expected: both buttons on one line per card; identical button `y` and
  identical distance to the card bottom across all cards (3 px tolerance),
  buttons near the bottom (≤ 30 px).
- Red (pristine HEAD, with the cards' entry animation disabled for a stable
  measurement):
  `AssertionError: 21.0 not less than or equal to 3 : Die Aktionsknöpfe liegen nicht auf derselben Höhe über allen Karten: [403.375, 403.375, 403.375, 424.375, 403.375]`.
  The `vibe-agent` card pushes its buttons 21 px lower than the others because
  the action row has no `margin-top:auto` / flex stretching. An earlier version
  of the case measured during the fade-in animation and produced 3–4 px of
  noise; the test now sets `data-animations='off'` before measuring. No
  assertion threshold was relaxed.

### 3. Restore version selection

- Precondition: two saves on `tester` produce two backups — oldest contains
  `Globaler Agent`, newest contains `Zwischenstand`; current file is `Aktuell`.
  The editor is re-opened so `GET /api/agent` supplies the backup list.
- Action: open restore confirmation, count options of the version chooser,
  select the **oldest** backup by its file name, confirm.
- Expected: chooser exists with ≥ 2 options; the oldest backup is selectable;
  after confirmation the file contains `Globaler Agent` and no longer contains
  `Zwischenstand` (proves a non-default version was restored).
- Red (pristine HEAD):
  `AssertionError: 1 != 0 : Die Restore-Bestätigung bietet keine Versionsauswahl (select) an`.
  Baseline `nova-agents.js:817-831` had no chooser and sent
  `{action:'restore', scope, name}` with no `backup`.
- Backend contract check (case 6): `vibe.agent_restore(scope, name, backup)`
  and `POST /api/agent` already accept a specific backup; case 6 was **green
  on pristine HEAD** and is deliberately kept as contract documentation, not
  as manufactured red evidence.

### 4a. Assignment checkbox accessible label

- Precondition: editor `tester`, `details[data-nv-assignments]` expanded.
- Action: query the checkbox by accessible role and a name matching
  `assign|zugewiesen` (case-insensitive).
- Expected: at least one such checkbox and the `proj` toggle among them.
- Red (pristine HEAD):
  `AssertionError: 0 not greater than or equal to 1 : Keine Projekt-Checkbox hat eine ausdrückliche 'Assign'/'Zugewiesen'-Beschriftung; zugängliche Namen: ['Agent in project: tester · proj']`.
- Intermediate coder state: the checkbox was wrapped in
  `<label class="nv-assign-toggle">…Zugewiesen</label>` but still carried
  `aria-label = "Agent in Projekt: tester · proj"`; because `aria-label`
  overrides the wrapping label text in the accessibility tree, the case stayed
  red until the coder extended the accessible name to include
  `Assign`/`Zugewiesen`. It is green in the latest worktree run.

### 4b. One assignment row per project

- Precondition: two projects (`proj`, `zweitprojekt`) present from server
  startup (new `AssignmentLayoutTest.setUpClass` adds the second project before
  the first request, avoiding the 2 s `project_map()` cache), editor expanded.
- Action: for each `[data-nv-assign]` checkbox, inspect its row container
  (`[data-nv-assign-row]` or parent) via `evaluate`.
- Expected: exactly two rows, one per project; each row contains exactly one
  checkbox and its `[data-nv-assign-model]` combobox; project name visible in
  the row text.
- Red (pristine HEAD):
  `AssertionError: 1 != 2 : Projekt 'proj' hat nicht genau eine eigene Zeile: [{'project': 'proj', 'rowText': '⌕⌕', 'checkboxesInRow': 2, 'modelInRow': True}, ...]`.
  Baseline `renderAssignments` appended `row.toggle` and `row.model` as
  separate siblings into `.nv-list` (no row, no project name).

## Red-phase commands and observed output

Pristine baseline (authoritative red evidence):

```
cd <package-worktree>
PRISTINE=/dev/shm/vibe-sandbox-1000/vibe-949edb757a/tmp/opencode/pristine
rm -rf "$PRISTINE" && mkdir -p "$PRISTINE"
git archive HEAD | tar -x -C "$PRISTINE"
cp tests/browser/test_agents_ui.py "$PRISTINE/tests/browser/test_agents_ui.py"
cp tests/unit/test_agent_management.py "$PRISTINE/tests/unit/test_agent_management.py"
cd "$PRISTINE"
python3 -m unittest \
  tests.browser.test_agents_ui.ListTest.test_header_search_and_new_agent_share_a_vertical_center \
  tests.browser.test_agents_ui.ListTest.test_agent_card_action_buttons_are_bottom_aligned_across_cards \
  tests.browser.test_agents_ui.StructuredEditorTest.test_restore_selects_an_older_backup_and_restores_that_version \
  tests.browser.test_agents_ui.AssignmentTest.test_assignment_checkbox_has_an_explicit_assign_label \
  tests.browser.test_agents_ui.AssignmentLayoutTest.test_each_project_renders_exactly_one_assignment_row_with_visible_name \
  tests.unit.test_agent_management.RestoreTest.test_restore_uses_an_explicitly_chosen_older_backup \
  -v
```
Observed (after the animation-stability edit): `Ran 6 tests`,
`FAILED (failures=5)` — cases 1–5 fail for the intended reasons quoted above;
case 6 `ok`. Full log:
`/dev/shm/vibe-sandbox-1000/vibe-949edb757a/tmp/opencode/pristine_red_v2.txt`
(earlier run: `…/pristine_red.txt`).

Same command in the assigned worktree once the coder's changes had landed:
`Ran 6 tests`, `FAILED (failures=1)` — only the header case (1) is still red;
card alignment (2), restore selection (3), accessible label (4a),
one-row-per-project (4b) and the backend contract (6) are `ok`. Log:
`/dev/shm/vibe-sandbox-1000/vibe-949edb757a/tmp/opencode/current_v2.txt`.
An earlier intermediate run (`…/run2.txt`) showed cases 1, 2 and 4a red.

Re-run green phase after implementation (from the assigned worktree):

```
cd <package-worktree>
python3 -m unittest \
  tests.browser.test_agents_ui.ListTest.test_header_search_and_new_agent_share_a_vertical_center \
  tests.browser.test_agents_ui.ListTest.test_agent_card_action_buttons_are_bottom_aligned_across_cards \
  tests.browser.test_agents_ui.StructuredEditorTest.test_restore_selects_an_older_backup_and_restores_that_version \
  tests.browser.test_agents_ui.AssignmentTest.test_assignment_checkbox_has_an_explicit_assign_label \
  tests.browser.test_agents_ui.AssignmentLayoutTest.test_each_project_renders_exactly_one_assignment_row_with_visible_name \
  tests.unit.test_agent_management.RestoreTest.test_restore_uses_an_explicitly_chosen_older_backup \
  -v
```

## Existing tests that already prove unchanged contracts

- `StructuredEditorTest.test_restore_brings_back_the_previous_version`
  (`test_agents_ui.py:1987` before my edits): restoring the newest backup still
  works; must stay green.
- `StructuredEditorTest.test_backup_action_creates_a_backup_entry`: backup
  creation and file placement unchanged.
- `AssignmentTest.test_project_toggle_and_model_override_are_saved`: assignment
  save/reload round trip must stay green.
- `tests/unit/test_agent_management.py::RestoreTest.test_restore_brings_back_the_previous_version`
  and `…::test_backups_of_a_similarly_named_agent_are_not_offered_or_restored`:
  backend restore and the negative "foreign backup is rejected" contract.
- `tests/unit/test_agent_management.py::ApiTest.test_api_restores_a_backup`
  (`:827`): `POST /api/agent` with `action:'restore', backup:<name>` already
  restores the named backup — the backend side of requirement 3 needs no change.

## Visual verification (supplementary)

Requirements 1 and 2 are layout-only; the deterministic bounding-box
assertions above are the primary evidence and follow an existing project
convention (`AgentListTest.test_name_and_tags_are_separate_rows` uses
`bounding_box()`). Screenshots were additionally taken from the **isolated
server** at viewport 1500×1100 (temporary sandbox paths, not repository docs):

| Screenshot | Acceptance criteria shown | Result in current state |
|---|---|---|
| `…/shots/gh109_agents_list.png` | 1 (header) and 2 (card buttons) | **Both met.** Title, search input and “New agent” button now share centre y = 111 px (was 113/111/119); equal 12 px gaps. Edit/Delete sit on one bottom-aligned line on every card, including the taller `vibe-agent` card. No visual deviation found. |
| `…/shots/gh109_assignment_rows.png` | 4 (assignment row) | **Met.** One row shows the visible project name `proj`, the `Assign` checkbox (now the accessible name too) and the model override together. No layout overlap visible. |
| `…/shots/gh109_restore_versions.png` | 3 (version selection) | **Met.** The restore confirmation shows a labelled `Select backup` dropdown with a `Newest first` hint and a confirmation button; the automated case proves an older chosen backup is actually restored, not just the newest. |

(Base path for the three files:
`/dev/shm/vibe-sandbox-1000/vibe-949edb757a/tmp/opencode/`.) These screenshots
were taken **after** the final production changes from the isolated server at
1500×1100 with entry animations disabled for stable geometry.

## Green phase and final status

Command (same six cases as the red phase, from the assigned worktree):

```
cd <package-worktree>
python3 -m unittest \
  tests.browser.test_agents_ui.ListTest.test_header_search_and_new_agent_share_a_vertical_center \
  tests.browser.test_agents_ui.ListTest.test_agent_card_action_buttons_are_bottom_aligned_across_cards \
  tests.browser.test_agents_ui.StructuredEditorTest.test_restore_selects_an_older_backup_and_restores_that_version \
  tests.browser.test_agents_ui.AssignmentTest.test_assignment_checkbox_has_an_explicit_assign_label \
  tests.browser.test_agents_ui.AssignmentLayoutTest.test_each_project_renders_exactly_one_assignment_row_with_visible_name \
  tests.unit.test_agent_management.RestoreTest.test_restore_uses_an_explicitly_chosen_older_backup \
  -v
```

Observed: `Ran 6 tests in 8.103s` — `OK` (all six green). Log:
`/dev/shm/vibe-sandbox-1000/vibe-949edb757a/tmp/opencode/current_v3.txt`.
Broader check of the affected classes (`ListTest`, `StructuredEditorTest`,
`AssignmentTest`, `AssignmentLayoutTest`, `RestoreTest`):
`Ran 19 tests in 17.150s` — `OK`. Log:
`/dev/shm/vibe-sandbox-1000/vibe-949edb757a/tmp/opencode/classes_final.txt`.
No neighbouring regression observed.

All four ticket requirements are covered by a red→green case pair, except the
backend half of requirement 3, which was already implemented in HEAD and is
documented as a green contract proof (case 6). No assertion was weakened; the
only test-side adjustment was disabling the fade-in animation before measuring
card geometry.

Material gaps: mobile-viewport screenshots were not taken; requirement 1/2
verification is desktop-only (1500×1100), and the geometry assertions use a
4 px/3 px visual tolerance rather than pixel equality.
