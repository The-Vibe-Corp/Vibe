# Independent Review — Work Package GH-98

**Scope reviewed:** branch `feature/korbat/gh-98`, start commit `7f91855`, HEAD = start commit + uncommitted working-tree changes (11 files per orchestrator's change-set statement). Worktree inspected: `/var/log/custom/vibe-dev/worktrees/vibe-GH-98-H9p58c`.

## Summary

The package translates the eight `SPEC.md` section headers written by the project assistant to fixed English while leaving all display logic (German step titles, `gt()` German passthrough, nova title mapping) untouched. The implementation is minimal and correct, the new tests prove the acceptance criteria directly and were not weakened, and the baseline/pin updates are scoped and legitimate. No Critical, High, or Medium findings.

**Findings: 0 Critical / 0 High / 0 Medium / 2 Minor (suggestions, non-blocking).**

## Acceptance criteria

| # | Criterion | Status | Location & evidence |
|---|---|---|---|
| 1 | Headers always English, independent of UI language and entered language | **PASS** | `bin/vibe_guide.py:55,63,71,79,87,95,103,111` — headings are constants in `STEPS`, no i18n coupling. Evidence: `test_new_spec_uses_exactly_the_eight_english_section_headings` (`tests/unit/test_project_guide.py:150-167`, exact ordered list equality of the eight English headings) and the German-absence assertions at `:137-141`; browser check `tests/browser/test_project_guide_ui.py:197-199`. Supplied green runs corroborate. |
| 2 | Text under those sections reliably pulled back into the boxes | **PASS** | `state()` keys off `entry["heading"]` (`bin/vibe_guide.py:320`), `apply()` off `sections.get(entry["heading"])` / `_set_section(..., entry["heading"], ...)` (`:432-438`). Evidence: `test_state_pulls_sections_from_english_spec_headings` (`tests/unit/test_project_guide.py:169-195` — an existing English-header SPEC fills all eight boxes, statuses `gefüllt`, `open == []`) and `test_apply_preserves_and_updates_english_spec_sections` (`:197-239` — keep-without-replace, replace-updates-named-section, final heading list re-asserted). |
| 3 | Wording follows the repo's own SPEC.md where a counterpart exists | **PASS** | Repo `SPEC.md` `##` headings verified by grep: `Product goal` (:8), `Target environment` (:23), `Functional scope` (:50), `Quality and acceptance` (:232), `Out of scope` (:240), `Locked decisions` (:248), `Audience and use` (:258) — 7/8 exact matches. `Open questions` has no counterpart; the established UI translation (`GUIDE_TEXT` `"Offene Fragen": "Open questions"`, `bin/web/app.js:184`) was used and documented (`docs/features/GH-98.md:27-31`). Faithful to the ticket's "you can use those". |
| 4 | No other logic changed; German UI behavior preserved | **PASS** (within limits below) | `STEPS[*]["title"]` unchanged (`bin/vibe_guide.py:54-110`); `gt()` returns raw text unless locale is `en` (`bin/web/app.js:194`); only the three stated `GUIDE_TEXT` values changed (`:166,169,181`); `nova-project.js` title mapping keys off the unchanged `step.title` (`:1510-1514`); `i18n.js` contains no guide-title entries. German-mode i18n expectations still assert `Zielgruppe und Nutzung` / `Funktionsumfang` / `Decisions Locked` (`tests/browser/test_i18n_ui.py:1272-1289`). |
| 5 | Manifest consistency | **PASS** | `docs/import-manifest.json:3-12` (GH-98 entry, date, reason); files entries `:1826-1830` (27195 / `e6c6c687…`) and `:1916-1920` (153244 / `f31477bd…`) match the claims. The app.js hash is independently corroborated: it equals the pin in `tests/unit/test_ui_style_reference.py:29`, whose supplied run (3 OK) recomputes the real file hash. `check-import-manifest.py` exit 0 is supplied evidence. |
| 6 | Living docs accurate | **PASS** | `docs/features/F9.md:49-60` states exactly the implemented behavior (titles unchanged, fixed English headings, exactly these read back, stable order). `docs/features/GH-98.md` mapping table matches the code. |

## Explicit assessments requested

**Baseline updates — legitimate.** `tests/verify-baseline.json` matches the claims exactly: label `pi-aarch64-py3.14-namespaces` gained/replaced the four entries (`test_github_issues` `05d45da9…` :13-16, `test_license` `b50b11f0…` :18-21, `test_release` `43897cf9…` :78-81, `test_repository_hygiene` `9a40be07…` :8-11); `min_tests: 2500` unchanged (:3); the `head_of_vibe` label is separate and untouched (:119-197). The four modules are unrelated to this package's code changes (home-path scan lists, license check); the only package-caused failure — the `app.js` byte-pin in `test_ui_style_reference` — was fixed through the test-owned pin, not the baseline, which is the correct mechanism and does not mask anything. The claim that identical signatures exist at start commit `7f91855` is supplied evidence I could not re-execute.

**GUIDE_TEXT alignment — faithful to ticket intent.** Aligning the three English UI titles to the exact file headings (`Audience and use`, `Functional scope`, `Locked decisions`) directly serves the ticket's anti-"correction" rationale: in the English UI every step title now equals the heading the assistant writes, so copying the title cannot break round-tripping. German mode is unaffected because `gt()` only translates when locale is `en`. The residual quirk that the German UI shows the mixed-language title "Decisions Locked" is pre-existing and explicitly protected by the ticket's "do not change any other logic" — correctly left alone.

**Test quality — not weakened, strengthened.** The heading assertions moved from substring to exact ordered-list equality (`:153-167`, `:227-239`); the new pull test exercises a pre-existing English-header file end-to-end through `state()`; the i18n forbidden-language lists are applied to each rendered step's text (`test_i18n_ui.py:1334-1339`), so the new entries (`Funktionsumfang`/`Decisions Locked` in EN, `Functional scope`/`Locked decisions` in DE) are real negative coverage. The `test_project_ui.py` fixtures keep the placeholder bodies in the six open sections, preserving the "1 of 8 filled" semantics (:1559-1584). No repo-wide leftover consumer of the old German SPEC headings exists (remaining hits are display titles, docs, and a historical review record).

## Findings

**Required fixes:** none.

**Suggestions (non-blocking):**
1. `docs/features/GH-98.md:97` links to `docs/reviews/GH-98-review-1.md`, which does not exist yet at review time. This self-resolves when the coordinator saves this report to that path; if the round numbering ever changes, the link would dangle. Suggestion only.
2. The i18n test's `forbidden` list is checked against the guide header bar and each step's text, but not the entire guide panel in one sweep; a German string leaking elsewhere in the card would not be caught by this helper. Pre-existing structure, out of scope for this package. Suggestion only.

## Verification limits

- Shell and Git execution are denied in this session: I could not run `git diff` against `7f91855`, recompute SHA-256/byte sizes, or execute tests. The "only these lines changed" claim, the hash values, and all test/check results (focused runs, `verify.sh quick/package/full` → exit 0, BASELINE-OK, 2797 tests, red phase) are supplied evidence; I verified their internal consistency and cross-corroboration statically (notably the app.js manifest hash vs. the style-reference pin).
- The 11-file change-set enumeration rests on the orchestrator's statement; my own sweeps found no stray artifacts (`.rej`/`.orig`/`.bak`: none) and `TICKET-GH-98.json` is untouched (`state: in-progress`, empty `commit`), as required pre-commit.
- No secrets or private paths introduced by the inspected files.

Verdict: PASS
