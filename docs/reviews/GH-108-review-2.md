# Focused Re-Review — GH-108 (round 2): round-1 blocker resolution

**Scope reviewed:** only the round-1 Medium blocker (in-progress detail showing the runner notice alongside the new draft/open select) and its immediate fallout.

## Findings from the correction

1. **Round-1 blocker resolved — confirmed in source.** In `bin/web/nova-project.js` (`nvpOpenTicketDetail`), the `if (rawState === 'in-progress') { … data-nv-runner-state-notice … }` branch is gone. The protected branch now reads `if (rawState === 'blocked' || rawState === 'waiting-merge')` and appends the runner notice; the remaining else branch (in-progress, open, draft) appends the `data-nv-ticket-state-select` and the `ticket-state-save` button. In-progress therefore still receives the select + save and no longer receives the contradictory notice. Fix location: `bin/web/nova-project.js:899–933`.

2. **Protected states intact.** Done notice (`data-nv-done-notice`) at `nova-project.js:900–903`; blocked/waiting-merge runner notice at `nova-project.js:906–910` — both unchanged. Browser contracts re-confirmed: `WorkStateOwnershipTest.test_runner_owned_blocked_and_waiting_states_have_no_control` (blocked/waiting-merge: no select, no save button, notice visible, state untouched) and ticket-dashboard done/blocked contract tests.

3. **New assertions meaningful and not weakened.** Browser: `test_detail_can_move_an_in_progress_ticket_back_to_draft` now asserts `select count == 1` **and** `notice count == 0` ("In Progress zeigt trotz Zustandsauswahl den Läufer-Hinweis") before selecting `draft` and saving. The notice assertion is additive and directly encodes the corrected contract. Unit: added `assertNotRegex(self.js, r"rawState\s*===\s*'in-progress'[\s\S]{0,300}data-nv-runner-state-notice", …)` — fails pre-fix, passes post-fix, and does not weaken the blocked/waiting-merge assertions.

4. **Docs/manifest consistent.** `docs/features/GH-108.md` gained the "Post-review correction (round 1)" section; verification notes updated; round-2 review reference added. `docs/import-manifest.json` shows refreshed post-fix entry for `bin/web/nova-project.js` (bytes 130441, sha256 `69c9ffb6…`, changed from pre-fix 130703 / `62447de7…`); checker reported 70 files OK.

## Verification limits

Independent re-run was not possible in this session (shell access unavailable); reliance is on the supplied red/green evidence (pre-fix isolated reproduction red, post-fix green, protected-state recheck 13 OK, `node --check` OK, manifest checker OK, `verify.sh quick` Exit 0).

## Conclusion

The round-1 Medium blocker is fully resolved in code, covered by meaningful red/green assertions, with protected states and documentation consistent.

Verdict: PASS
