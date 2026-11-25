# Independent Review — GH-70 "Clean up documentation"

**Reviewed revision:** uncommitted working-tree changes on top of `9868e96` (origin/dev), worktree `/var/log/custom/vibe-dev/worktrees/vibe-GH-70-YqrOtW`, branch `feature/korbat/gh-70`.

**Summary:** The change set adds a well-built English feature index (`docs/features/README.md`) and 12 living feature docs under `docs/features/current/`, plus one navigation bullet each in `README.md` and `docs/handbuch.md`. All 129 record files map 1:1 to index links, all sampled factual claims in the living docs match SPEC.md and the implementation exactly, and all 9 documented discrepancies are correctly attributed. Two minor wording suggestions, no blockers.

**Finding counts:** Critical 0 · High 0 · Medium 0 · Minor 2

## Review questions

**1. Scope/preservation — PASS with stated limit.** Shell/git access was denied for this review session, so I could not run `git diff` against `9868e96` myself; the exact diff boundary rests on the tester's L1/L3 evidence (15 changed/new markdown files, no record edited, 0 new unresolved refs). Everything I inspected directly is consistent with the claim: only the announced docs exist as new/changed content; no code or test file was observed modified; `docs/reviews/` is populated and intact; `docs/features/B7-subagent-permissions.md:109` contains the literal user home path (`/home/<user>/...`) required by the baseline test signature (the original review quoted the concrete literal; the coordinator replaced the quote with this placeholder because the release hygiene scanner flags that path in repository files, which would change the accepted baseline signature) (byte-identity to the baseline itself: NOT VERIFIED by me, no git access — but the required literal is present and no record file was edited per L3).

**2. Index quality — verified.** 129 record links (grep count) = 129 record files on disk (31 AP + 22 B + 34 F + 12 GH + 26 V + 4 descriptive slugs); nothing on disk is missing from the index. I spot-checked ~30 H1 titles (AP15, F13, F14, F2, F9, V-008, AP11, B1-ticketlogik, F1, GH-48, AP05, B5, GH-58, AP01, AP02, B2, V-007, AP14, B20, V-001, AP1, B4-install, B7, B7-subagent-permissions, B3 vs B3-wartet, B6 vs B6-statusmarken, GH-56, GH-56-design-notes, worknotes-nachweis-sync, fix-opencode-password-env) — all group assignments and one-line summaries match. Collision facts verified: the five B-ID pairs cover distinct topics; `AP1.md` vs `AP01.md` are different topics; `AP7.md` exists and no `AP07.md` exists; the AP*-Korbat series is present; B10/B15/B19 exist nowhere on disk; GH-56/GH-56-design-notes are the same package.

**3. Living-doc content accuracy — verified, no contradictions.** Sampled claims, all exact in code: STATES/TYPES/TYPE_PREFIXES (`bin/vibe_tickets.py:28–30`); `DEFAULT_PACKAGE_BRANCH_PATTERN = "feature/{owner}/{id}"` and the full gate check (state done, non-empty test, commit exists, `docs/features/<ID>.md`, newest review with `Verdict: PASS`, already-integrated case) (`bin/vibe_packages.py:398, 1161–1235`); `PROJECT_AGENTS_VERSION = 3` (`bin/vibe:3787`); 90-day stale-price rule (`bin/vibe_models.py:20`); harness selection (`bin/vibe_harness.py:11–37`); MCP config-file order and limits 5–90 s / 5–60 s, 200 tools, 4 MiB stdio, 1 MiB HTTP (`bin/vibe_mcp.py:220–232, 615–623`); exit codes 3/4/5/6/7 (`scripts/verify_engine.py:57–64`); baseline `min_tests` 2500 and env `pi-aarch64-py3.14-namespaces` (`tests/verify-baseline.json`); write-dir default `/tmp/opencode` + project dir (`bin/vibe_sandbox.py:69`, `bin/vibe:558`); project type markers (`bin/vibe:423–426`).

**4. Discrepancy section — all 9 plausible and correctly attributed.** Directly verified: AP05.md:53 states `vibe/<name>-<ID>-<zeit>-<pid>` and AP05.md:65/87 the TICKETS.md/FEEDBACK.md gate (both historical vs. current code); B6-statusmarken vs. `STATES`; F9 vs. `vibe_guide.FILES` = SPEC.md, AGENTS.md, `.vibe/project.env`, README.md (`bin/vibe_guide.py:118–123`); F13 four tabs vs. five (`bin/web/nova-project.js:2133`); agent-config version 2/1 vs. 3; `verify.py` as compat shim (`scripts/verify.py:1–8`); V-001's "22 entries" (V-001.md:16) vs. exactly 71 manifest entries (grep count); audit-log gap correctly traced to SPEC.md:20 and honestly hedged as an open gap. Nothing is mislabeled as a discrepancy.

**5. Language/structure — PASS.** All 12 living docs are in English with the status/authority header (`Status: current as of 2026-11-25 … Authority: SPEC.md`) on line 3, and all record links are relative (`../<ID>.md`) to files that exist; related-docs links in the index all resolve.

**6. Acceptance — met.** A reader can reach current behavior per feature (index → 12 living docs) and trace history per package (129 one-line record links). Living docs are new current-behavior prose, not copies of records; no duplication observed in reading, and tester L3 reports longest verbatim run = 0. Package checks were supplied (quick exit 0; full exit 0 BASELINE-OK, tests=2721) and were not rerun per instructions; no application/test changes observed. Historical reports untouched.

## Minor suggestions (non-blocking)

1. `docs/features/README.md:216` — "B1.md additionally contains three appended same-ID sections: cost table (2026-11-07) …" is slightly loose: the cost table (2026-11-07) is the record's original entry (H1 at line 1, `Stand: 2026-11-07` at line 3); only the 2026-11-20 and 2026-11-24 sections are appended. Rewording to "three same-ID entries (the original cost-table record plus two appended sections)" would be exact. Dates, topics, and the cross-link (B1.md:450) are already correct.
2. `docs/features/README.md:220` — the missing-files note covers B10/B15/B19 but not V-012, which is likewise absent from disk and index. Adding it would make the series-gap note symmetric. Optional.

## Verification limits

- No git execution was possible (shell permission denied); the exact change-set boundary vs. `9868e96` and byte-identity of untouched files (records, reviews, B7:109) rest on the supplied tester evidence L1/L3, which is internally consistent with everything I could inspect directly.
- Heavy suites not rerun per instructions; check results are supplied tester evidence, not my own runs.
- Note: the supplied change-set description says "14 groups"; the index actually has 13 `###` groups (the artifact itself makes no count claim, so this is a summary inaccuracy, not a document defect).

Verdict: PASS
