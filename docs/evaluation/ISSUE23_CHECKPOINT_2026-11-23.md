# Formal core checkpoint and reporting

This record supports [Issue #23](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/23) and the [frozen evaluation protocol](ISSUE22_2026-11-23.md). It identifies the evidence available at the proposed reporting boundary and how to document later results.

## Proposed reporting boundary

The [remote checkpoint](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/blob/codex/issue23-live-results/docs/evaluation/evidence/issue23/live/live-progress.json) generated on 2026-11-23 at 21:56:59 Asia/Shanghai contains 672 recorded attempts from 21 complete blocks. There are 653 completed tasks and 19 errors. The formal plan contains 1,152 attempts. Coverage is reported as of the snapshot.

| Reference | Identifier |
| --- | --- |
| Checkpoint Git blob | `6a21baa580686eb247ebf6ed902b7c2bdef2a521` |
| Run ledger SHA-256 reported by the checkpoint | `7bdc26a53e24fdfc18598f13b95e395a28bce7bf66de14556b7116a95b116315` |
| Score SHA-256 reported by the checkpoint | `bbbd4b92a62942aae8397f0a6b106a7ea65159aef39097ea0247b152542309e5` |
| Frozen plan SHA-256 reported by the checkpoint | `9e77ec98d468dc7631a754a57fb750d20233556a9588ad4bc875a18e3f9e690e` |
| Formal protocol identifier reported by the checkpoint | `996a654ebc6b0486015d767e856bffa3369401ad5dc5de90639eff9c4aba86f3` |

Use the end of the 672-attempt checkpoint as the proposed boundary. Confirm the actual boundary from the first affected run record before assigning any result to a new execution period. The snapshot timestamp records its generation time.

## Report results across the boundary

- Preserve the original checkpoint and its error records. For each period, give the number planned, recorded, completed, failed, and missing. Report unknown delivery separately and use the frozen grading rules.
- Attach the evidence revision and the actual execution period to each result. Flag cases where the run records cannot establish the period. Keep later corrections traceable to the original attempt record.
- Report outcomes separately by period. The cases covered and provider conditions can differ across periods. Raw rate differences alone cannot establish an effect of the execution change. If the report also includes totals, show the per-period counts alongside them.

## Review checks

- Check that the remote snapshot matches the identifiers and the 672 recorded attempts above.
- Confirm that the execution boundary and period labels match the available run records.
- Reconcile recorded attempts against the frozen plan. Retain errors and note missing records before calculating rates.
- Cite the checkpoint revision and evidence location in each review finding.
