# H1 engineering verification — 2026-11-15

Environment: Windows, Python 3.13.5, synthetic T01 fixture. Base: main `4ea0413f9d72b35a4e196b76987336d93ceda57f`. All requests used scripted responses or local loopback HTTP; paid API calls: **0**.

## Prerequisites

Before implementation, #3, #7 and #9 were CLOSED and their required PRs were merged into main: #4 (`e2e5e35`), #45 (`62cb371`) and #54 (`1f65c33`). The issue body, native blocked-by links and roadmap #27 agreed. The authenticated account was `cynic004`, the assigned owner; designated reviewer: `qikhcysa`.

The final implementation includes the subsequently merged #12/PR #56 F1 path through main `4ea0413`. Its scheduling and recovery behavior remains intact.

## Commands and observed results

From the repository root:

```text
python -m unittest discover -s tests
Ran 150 tests ... OK

python -m contracts.validate
VALID bundle: attacked-h1.json
VALID bundle: benign-h0.json

python -m compileall -q agent_privacy tests contracts member_a
Passed

git diff --check origin/main
Passed
```

The 24 new tests comprise 15 generation/cache tests and 9 continuation tests. They cover malformed/truncated model output, duplicate/nonfinite JSON, no-tools summary generation, evidence corruption, wrong user/task/input conditions, failed generation without retries, concurrent reservations, and load/continue in fresh processes. H1 checks include exact loopback request bytes and header-only credentials, unchanged desktop metadata, rejected foreign handles, rejected foreign-task loads before any send, and recovery state reset after a previous F1 attempt.

From `member_a/`:

```text
python verify.py --output runs/issue11-regression
unit_tests=59, failures=0, errors=0, all_passed=true, paid_api_calls=0
```

All six original cross-process scenarios passed, including S0/S1/S2/S3 cases and the expected double-scheduler failure outcome. This is regression evidence for the original offline component, separate from the new hosted-path tests.

Loopback checks initially failed under restricted local networking, then passed with local communication permitted. The final 150-test result includes every loopback test; no tests were skipped.

## Observed H1 trace

[Captured synthetic observation](evidence/H1_2026-11-15.json) records one summary generation followed by two fresh mobile attempts. Generation was requested once; preparing the same cache again returned the same artifact without another request.

| Condition | Result | Controller sends | Tool calls | Active bindings before/after reset |
| --- | --- | ---: | ---: | --- |
| S0/H1/F0 | completed; bundle valid | 3 | 2 | 6 / 0 |
| S0/H1/F1 | completed; bundle valid | 4 | 3 | 6 / 0 |

The two attempts have different session/trial IDs and identical handoff artifact IDs, summary handles and original source metadata. Each load decision precedes `context_loaded`; the loaded role is `tool`, while the immutable summary metadata retains `message_role: assistant`, `source: model_summary`, untrusted integrity and its original desktop scope. The original document remains the summary's derivation parent. Conversations are cleared and audit files remain after both resets.

The six S0/S1/S2 × F0/F1 adapter boundary probes reuse that frozen summary without generating another. They validate condition-independent artifact use at the existing egress boundary; they do not establish complete S1/S2 hosted loops. Full integration remains #20.

The observation file includes raw load-event metadata and manifest hashes. Full local request/response archives are retained under `artifacts/issue11-final-observation/`; original offline regression output is under `member_a/runs/issue11-regression/`. These ignored development directories are local evidence, not shared download locations. The committed tests reproduce the documented invariants and create their own temporary archives.

## Limits and assistance

No live hosted H1 API call, formal experiment, attack-success rate, or agenda semantic approval is claimed. Cache hashes detect corruption, not a coherent rewrite by the owner of trusted cache storage. S1–S3 hosted orchestration and formal scoring remain separate work.

Codex implemented and checked the changes, including supplementary independent AI code review and compatibility with the latest main. A different human teammate must inspect/reproduce the latest commit before merge. No human approval, merge, or implementation-issue closure was performed.
