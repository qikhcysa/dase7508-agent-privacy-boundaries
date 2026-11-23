# Parallel support for the formal evaluation

Use this plan to review evidence and prepare deliverables while the formal runs are in progress. The formal operator and execution order follow the [frozen protocol](ISSUE22_2026-11-23.md). [Issue #23](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/23) remains the owner of the core run. [Issue #24](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/24) remains the owner of the supplement run. Record development checks as separate engineering evidence.

## Proposed division of work

| Member | Work that can proceed now | Deliverable |
| --- | --- | --- |
| XIA Liyuan (`Sherlyn-Xia`) | Operate the scheduled formal run and publish the latest available checkpoint. | Checkpoint link, source revision, recorded count, spend status, and any blocker. |
| JIN Zhan (`jinzhan857-sketch`) | Review the archived attempt counts and budget evidence while the operator runs. Check for missing or duplicate attempt IDs and reconcile errors with the reported denominator. | Review notes keyed to the checkpoint and attempt IDs that need follow-up. |
| XIA Zhangning (`cynic004`) | Inspect reset and handoff evidence from completed attempts. Where a fresh smoke check is needed, use a benign development fixture and scripted model responses offline. | List of completed checks, evidence paths, and exceptions that need an operator decision. |
| JIANG Hanyu (`unicjiang777`) | Check that records needed for the later exposure and lawful-sharing audit are present. Prepare the audit table and final report outline. | Evidence inventory and an empty results table ready for final figures. |
| ZHANG Xilong (`qikhcysa`) | Reconcile open findings across the reviewers and prepare the consolidated handoff. | One status summary with the checkpoint link, outstanding decisions, and follow-up owners. |

## Checkpoint handoff

1. Use the existing checkpoint as a shared, read-only reference. Record its link and revision alongside each review so results from different snapshots stay traceable.
2. Each member can review their area without waiting for the other reviews. For each finding, record the affected attempt or artifact, the evidence path, the observation, and the owner of the next action. Share summaries and approved artifact links in the PR.
3. Route gaps, ambiguous delivery, and budget discrepancies to the formal operator. Preserve the original records and record any change to a reported count with its reason.
4. Prepare the report structure and validation notes during the run. Fill formal results and complete the downstream analysis, audit, and reproduction issues after their required inputs are delivered, as shown on the [roadmap](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/27).
