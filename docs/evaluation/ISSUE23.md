# Issue 23 formal core operator guide

This entry executes the dated protocol in
[`ISSUE22_2026-11-23.md`](ISSUE22_2026-11-23.md). It records the full frozen
1,152-condition plan, but sends at most one 32-condition block per invocation.
Every later invocation resumes only plan identifiers that have not started.
Physical retries and provider fallback are disabled.

The formal entry refuses to run unless the checkout is clean, the approved
protocol blob SHA-256 is
`996a654ebc6b0486015d767e856bffa3369401ad5dc5de90639eff9c4aba86f3`, and the
core-plan SHA-256 is
`8dad8653fd61e4282d1c9dc8838aa78eae731234847a124d6237e901268c3497`.
Formal bundles and summary-generation bundles contain `phase=formal` and the
protocol digest. The run ledger also records the execution commit and fixed
model ID.

## Prepare without API calls

From a clean checkout on the Issue 23 branch:

```sh
python -m contracts.validate
python -m agent_privacy.supplements --check
python -m agent_privacy.issue23 plan
python -m agent_privacy.issue23 status
```

`plan` creates `artifacts/issue23-operator/`, its immutable plan and the SQLite
budget ledger. It sends no network request. Never delete or replace that
directory after a formal condition has started.

## Run one block

Before every block, reconcile the provider bill and supply three cumulative
amounts: the formal-stage total, today's Shanghai-time total, and the complete
project total. The first block may use zero only when those observed bills are
actually zero.

```sh
python -m agent_privacy.issue23 block \
  --formal-bill-cny 0 \
  --daily-bill-cny 0 \
  --project-bill-cny 0
```

The API key prompt is masked and the key is not saved. For a previously exported
`ZAI_API_KEY` (or `AGENT_API_KEY`), add `--non-interactive`. The budget transport reserves
0.8617984 CNY before every model request and applies the 20 CNY daily, 120 CNY
formal-stage and 500 CNY project caps. Missing usage or a transport interruption
retains the reservation and stops later sends for human reconciliation.

After a complete block, inspect its checkpoint under
`artifacts/issue23-operator/checkpoints/`, the run ledger, raw request evidence,
reset files and `score.json`. Reconcile the provider bill before invoking the
next block. Do not rerun failed conditions; the next invocation continues only
unstarted plan identifiers.

## Offline verification

```sh
python -m unittest tests.test_issue23 tests.test_runner -v
python -m unittest \
  tests.test_hosted.HostedTests.test_formal_attacked_s1_s2_records_protocol_identity \
  tests.test_handoff.HandoffTests.test_formal_generation_records_protocol_identity -v
```

The four loopback HTTP tests require permission to bind `127.0.0.1`; a restricted
sandbox can reject those tests before application code runs.
