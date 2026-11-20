# AP1 — Independent test-agent validation report

**Repository:** `/var/log/custom/vibe-dev/worktrees/vibe-AP1-nme5yF`
**Branch / HEAD:** `feature/korbat/ap1` / `8f26a85` (AP1 already contained via `976228b`)
**Scope:** tests and test evidence only. No production code, test files, or repository files were edited.
**User scope decisions recorded:** Trilium and GitHub actions are explicitly waived for this local follow-up. The separately running full suite ended with SIGTERM/exit 143 and will not be retried; **no full-suite pass is claimed.**

---

## 1. Acceptance checks derived from TICKETS/AP1 docs

These were derived from `TICKETS.md` AP1, `docs/features/AP1.md`, and the existing test contracts, independently of the implementation diff.

### Bug 1 — private server must belong to its target directory
- **AC1:** A live private server is reused only if it is HTTP-healthy **and** its recorded `write_dir` realpath matches the requested directory. A target change (`$P` → `$WT`, or AP1 → AP2) must stop the old server and start a new one with the new `--chdir`/`--write-dir`, then use the new URL.
- **AC2:** A server file without `write_dir` (old format) or with a different realpath must be treated as not reusable and restarted.
- **AC3:** The sandbox project argument remains `$P`; only `--chdir`/`--write-dir` follow the target. Sandbox state/session data stays per integration project.
- **AC4:** Existing end-of-run cleanup of the server file/process remains intact.

### Bug 2 — opencode credentials must reach the sandbox DB
- **AC5:** Before building bwrap argv, create `<state>/data/opencode/opencode.db` from the host DB (`$XDG_DATA_HOME/opencode/opencode.db`, else `~/.local/share/opencode/opencode.db`) using a read-only/immutable source.
- **AC6:** Copy schema plus only `credential`, `account`, `account_state`, `control_account`, `migration`; no session, message, blob, or kv rows.
- **AC7:** New target file is created atomically with mode `0600`.
- **AC8:** An existing sandbox DB with credential rows is left byte-for-byte untouched.
- **AC9:** Upgrade path: an existing empty `credential` table is filled transactionally while existing sessions/messages/kv remain untouched.
- **AC10:** Missing host DB or a source without a `credential` table must not abort; it creates no target or inserts no credentials, and warnings must not contain token values.
- **AC11:** The legacy `auth.json` `--ro-bind` behavior remains unchanged.
- **AC12:** The host DB is never written; the sandbox remains a write boundary.

---

## 2. Current implementation — focused green results

All commands ran on HEAD `8f26a85` with `PYTHONDONTWRITEBYTECODE=1`, isolated `HOME`/`XDG_DATA_HOME`, inherited `VIBE_*`/`SANDBOX` variables removed, and an approved temp directory.

### Combined AP1 run (authoritative focused result)
```text
python3 -m unittest \
  tests.unit.test_ap1_sandbox_credentials \
  tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest -v

Ran 7 tests in 8.010s
OK
EXIT=0
```

### Individual runs
```text
python3 -m unittest tests.unit.test_ap1_sandbox_credentials -v
Ran 6 tests in 0.070s
OK
EXIT=0

python3 -m unittest tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest -v
Ran 1 test in 9.232s
OK
EXIT=0
```

### Related regression suite
```text
python3 -m unittest tests.unit.test_b17_sandbox_argv -v
Ran 4 tests in 0.095s
OK
EXIT=0
```

### Complementary checks
```text
bash -n bin/vibe-run.sh          -> exit 0
AST parse of bin/vibe_sandbox.py -> OK
```
These are syntax checks only, not substitutes for the tests.

**Conclusion:** the current implementation passes all 7 focused AP1 tests and the 4 related sandbox-argv regression tests.

---

## 3. Pre-AP1 red evidence — successfully reproduced

A disposable export was created from `1de016b923f151da2e6c5f4c7d06883f0c5f3920` using `git archive`. Only these current test-side files were overlaid:

- `tests/unit/test_ap1_sandbox_credentials.py`
- `tests/unit/test_b13_private_server_runner.py`
- `tests/unit/runner_support.py`

Production files remained pre-fix:
- `bin/vibe-run.sh` SHA-256 verified equal to `1de016b`
- `bin/vibe_sandbox.py` SHA-256 verified equal to `1de016b`
- Both verified different from current HEAD
- All three overlaid test files verified equal to current HEAD

### Red — credential tests
```text
python3 -m unittest tests.unit.test_ap1_sandbox_credentials -v

Ran 6 tests in 0.112s
FAILED (failures=2)
EXIT=1
```

Failures:
```text
FAIL test_ak1_schema_and_credentials_are_copied_without_session_data
AssertionError: False is not true : Sandbox-DB wurde nicht angelegt

FAIL test_ak3_empty_credentials_are_filled_without_touching_sessions
AssertionError: Lists differ:
[('opencode-go', '<synthetic-fixture-token>')] != []
```

- **AK1** fails because pre-AP1 code never creates the sandbox DB.
- **AK3** fails because pre-AP1 code never fills the empty `credential` table.
- **AK2, AK4, AK5, AK6 pass pre-fix**; they are regression guards for “do not overwrite”, “missing source does not abort”, “old source does not abort”, and “auth.json binding unchanged”. They are not claimed as red-green evidence.

### Red — preflight target-change test
```text
python3 -m unittest \
  tests.unit.test_b13_private_server_runner.PreflightWriteDirChangeTest -v

Ran 1 test in 8.273s
FAILED (failures=1)
EXIT=1
```

Failure:
```text
AssertionError: 2 != 1 : Es wurden nicht zwei Server gestartet
(einer je Zielverzeichnis):
[{'event': 'listening', ..., 'cwd': '.../proj'}, ..., {'event': 'term'},
 {'event': 'exit'}]
```

Only one `listening` event was recorded, with `cwd=$P`; no second server was started for `$WT`. This is the exact bug described in AP1.

These red failures are genuine missing-fix failures, not environment errors: no bwrap is needed for these tests, no imports failed, and the assertion messages directly show the absent DB and the single reused server.

---

## 4. bwrap limitation — not a real sandbox run

The kernel does not permit unprivileged user namespaces in this environment:
```text
$ bwrap --ro-bind / / true
bwrap: No permissions to create a new namespace, likely because the kernel
does not allow non-privileged user namespaces.
```

Therefore:
- The real bwrap execution path was **not** verified here.
- DB seeding was tested through `bwrap_argv` with a `VIBE_BWRAP` stub; the sandbox was never actually launched.
- `SandboxPrivateServerTest` (real bwrap/sandbox-mode server test) was **not run**; its sandbox-mode path remains unverified in this environment.
- No claim is made that a sandboxed `opencode serve` actually saw the copied credentials.

---

## 5. Coverage assessment

| Acceptance area | Evidence | Status |
|---|---|---|
| AC1 server restart on `$P` → `$WT` | `PreflightWriteDirChangeTest` | Covered, green |
| AC2 stale/missing `write_dir` | Code inspection only; no dedicated test | Gap |
| AC3 sandbox argument remains `$P` | `SandboxPrivateServerTest` exists but needs bwrap; not run | Gap in this environment |
| AC5/6/7 seed DB, auth tables only, 0600 | AK1 | Covered, green |
| AC8 existing credentials untouched | AK2 (byte-identical) | Covered, green |
| AC9 upgrade empty credentials | AK3 | Covered, green |
| AC10 missing host DB / no credential table | AK4, AK5 | Covered, green |
| AC11 legacy `auth.json` binding | AK6 | Covered, green |
| AC12 host DB never written | Code inspection only; no byte-comparison assertion | Gap |
| Warning path with no token leakage on copy failure | Not explicitly tested | Gap |

### Additional tests/code changes needed?
- **No production-code changes are required** for AP1 based on the focused tests.
- **No blocking test changes** are required.
- Optional non-blocking follow-ups, if the project wants stronger regression coverage:
  1. A test for an old server file without `write_dir`.
  2. A test for a server file with a mismatched `write_dir`.
  3. An assertion that the host DB bytes are unchanged after seeding.
  4. A corrupt/unreadable host-DB test asserting warning on stderr and no token leakage.
  5. A sandbox-mode preflight restart test using the fake-bwrap path.
  6. A fallback-source-path test for `~/.local/share/opencode/opencode.db`.

---

## 6. Not run / not claimed

- **Full suite: not run by me and not passed.** The separately running full-suite wrapper ended SIGTERM/exit 143 and will not be retried. No full-suite result is claimed.
- **Coordinator-reported checks:** quick suite Exit 0 and package 11/11 Exit 0 are recorded as coordinator-reported, not independently reproduced here.
- **Real bwrap/sandbox execution:** not verified, as above.
- **Real opencode DB:** not read; no real credential, token, session, or personal config data was accessed. Tests used a synthetic SQLite schema and synthetic fixture values only.
- **Trilium and GitHub:** explicitly waived by the user for this local follow-up; no synchronization or GitHub actions were performed.

---

## 7. Cleanup and worktree state

- Disposable export and my focused-test logs were removed.
- I did not edit any repository file.
- `TICKETS.md` and `FEEDBACK.md` are unchanged (original mtimes).
- Worktree currently shows `M docs/features/AP1.md`; this concurrent documentation change was not made by me and was preserved. No test outputs or caches were left in the worktree.

---

## 8. Completion status

**Complete** for the requested independent AP1 focused validation.

- Current implementation: **passes** the 7 focused AP1 tests and the 4 related sandbox-argv tests.
- Pre-AP1 red phase: **reproduced** for both defects (credential copy: AK1/AK3; server target change: single reused server).
- Real sandbox/bwrap execution: **unverified due to kernel namespace restriction**.
- Full suite: **not passed / not claimed**; wrapper terminated by SIGTERM/exit 143 and will not be retried.
