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
