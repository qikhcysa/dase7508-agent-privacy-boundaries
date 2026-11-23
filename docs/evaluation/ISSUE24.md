# Issue 24 formal supplemental operator

This operator executes the 240 supplemental attempts frozen by
`ISSUE22_2026-11-23.md`. It keeps these results separate from the 1,152 core
attempts while inheriting the completed Issue 23 budget ledger, so both stages
remain under the same formal, daily, and project caps.

## Frozen layout

The committed supplement manifest expands in its original array order to:

- 48 lawful-sharing attempts under S3;
- 48 persistence chains, with task 1 immediately followed by task 2 (96 attempts);
- 96 H1 pressure attempts in which both schedulers time out.

The plan has eight bounded blocks. No block exceeds 32 attempts and no
persistence pair crosses a block boundary. There are no retries. Every ordinary
attempt uses a fresh registry and must pass the reset check. A task-1 H1 artifact
is the only retained input offered to the corresponding task 2; S3 records the
cross-task denial and the current task continues without promoting that summary.
Double-scheduler failure is retained as `double_scheduler_timeout` and is
excluded from normal slot utility.

## Initialize once

Run from a clean committed Issue 24 checkout after Issue 23 has finished and its
budget has no pending request:

```sh
python -m agent_privacy.issue24 plan \
  --prior-budget ../dase7508-issue23/artifacts/issue23-operator/budget.sqlite3
```

This command makes no API call. It writes the frozen plan, exact materialized
inputs, hashes, classification record, and an exact copy of the Issue 23 budget
database under `artifacts/issue24-operator/`.

## Run and reconcile blocks

Read the provider dashboard before each block and enter fresh cumulative values.
When all three provider values remain zero:

```sh
python -m agent_privacy.issue24 block \
  --formal-bill-cny 0 \
  --daily-bill-cny 0 \
  --project-bill-cny 0
```

Repeat the same command after each completed checkpoint, using updated dashboard
values if any value changes. The local token ledger remains conservative even
when the provider bill is zero. An unknown response retains its reservation and
stops before the next network request; preserve the evidence, reconcile the
dashboard, and then resume the same block. Never delete or edit a recorded try.

When `status` reports one pending request, reconcile it after checking the
dashboard. This retains the entire conservative reservation and never retries
the request:

```sh
python -m agent_privacy.issue24 reconcile \
  --formal-bill-cny 0 \
  --daily-bill-cny 0 \
  --project-bill-cny 0
```

The read-only status command makes no API call:

```sh
python -m agent_privacy.issue24 status
```

For a live read-only progress bar in a second terminal:

```sh
python -m agent_privacy.issue24 watch --interval 30
```

Evidence is stored under `artifacts/issue24-operator/`. `score.json` reports each
family separately, including lawful releases, persistence denials and old-marker
outbound observations, double timeouts, prohibited outbound requests, receiver
records, errors, usage, and missing attempts. Raw bundles and traces remain the
source of truth for the independent exposure audit.

## Limits

The operator does not turn an absent provider bill into proof of zero cost. It
records token-derived conservative usage and requires the human operator to
check the provider dashboard at every block boundary. Formal execution requires
one clean execution commit; changing code, the protocol, the supplement
manifest, the frozen plan, or archived input bytes stops resume.

## Parallel four-shard mode (optional scheduling variant)

The default single-operator flow above remains the authoritative protocol
baseline. When wall-clock time matters, the same frozen plan can be split into
four fixture-aligned shards under the dated parallel addendum
[`ISSUE24_PARALLEL_ADDENDUM_2026-11-24.md`](ISSUE24_PARALLEL_ADDENDUM_2026-11-24.md).
Prompts, tools, conditions, criteria, grading and the three spending caps are
unchanged; only scheduling and the operator count change.

| Shard | Member | GitHub account | Fixtures | Attempts |
| --- | --- | --- | --- | ---: |
| `w1` | XIA Zhangning | `cynic004` | B01-B03 | 60 |
| `w2` | XIA Liyuan | `Sherlyn-Xia` | B04-B06 | 60 |
| `w3` | JIN Zhan | `jinzhan857-sketch` | B07-B09 | 60 |
| `w4` | ZHANG Xilong | `qikhcysa` | B10-B12 | 60 |

A fixture has 20 attempts, so three fixtures per shard give exactly 60 attempts
per worker. Persistence pairs stay inside one shard, and every shared H1
snapshot key belongs to a single fixture, so no summary key crosses a worker.
No retries are added and every condition still runs at most once.

**Coordinator, once** (no API call):

```sh
python -m agent_privacy.issue24 plan --prior-budget ../dase7508-issue23/artifacts/issue23-operator/budget.sqlite3
python -m agent_privacy.issue24_parallel shard-plan
```

`shard-plan` writes `artifacts/issue24-operator/assignment.json` plus one
isolated root per worker under `artifacts/issue24-operator/shards/<worker>/`
(frozen shard plan, archived inputs, a copy of the inherited budget ledger and
its own classification record). The coordinator distributes the checkout and
each worker root to the corresponding operator.

**Each worker, in the worker's own root**:

```sh
python -m agent_privacy.issue24_parallel run-shard --worker w1 \
  --formal-bill-cny <...> --daily-bill-cny <...> --project-bill-cny <...> \
  --non-interactive
```

The command runs the remaining blocks of that shard through the owner's block
runner, so evidence layout, snapshot reuse, reset checks and score rows are the
same as the serial mode. It is resumable: recorded conditions are verified and
skipped, never repeated.

**Coordinator, after all four shards finish**:

```sh
python -m agent_privacy.issue24_parallel merge
python -m agent_privacy.issue24_parallel judge-summaries \
  --samples 3 --formal-bill-cny <...> --daily-bill-cny <...> --project-bill-cny <...>
```

`merge` refuses to run unless every planned condition is recorded exactly once,
re-checks reset evidence, merges the attempt and snapshot evidence, writes
`merged/score.json` (the owner's scorer and family aggregation) and
`merged/merge-report.json` (per-worker attempt counts and incremental
conservative spend). `judge-summaries` is analysis support for #31: a fixed,
hash-recorded prompt asks GLM-5.3-Flash, three samples per retained task-one
summary, whether the summary still carries the persistence instruction, and
writes `merged/summary-review.json` plus a per-sample JSONL. Its settings are
analysis settings, not frozen experiment settings; the exact summary text and a
teammate's reading remain authoritative.

Accounting in parallel mode: each worker holds a copy of the inherited budget
ledger, so the three caps are still enforced per worker; the coordinator sums
the incremental conservative usage after merge and reconciles the provider
dashboard. A pending request stops its own shard until that shard's operator
reconciles it; it never blocks the other shards.

The default single-operator flow is unchanged and should be used when the serial
protocol baseline is required.

