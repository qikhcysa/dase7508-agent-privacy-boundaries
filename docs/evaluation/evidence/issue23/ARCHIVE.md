# Issue 23 core evidence archive

The published snapshot records execution commit `518864f7535613d29c527a4f36143280f963f269`. The operator is XIA Liyuan. The run used the operator-local directory `artifacts/issue23-operator/`. A reviewer-accessible archive location is still pending.

| Path relative to the archive root | Evidence |
| --- | --- |
| `frozen-plan.json` | The 1,152 planned conditions and their order |
| `core/run-ledger.json` | Attempt keys, selected tries, recorded resets and snapshot references |
| `score.json` | Per-attempt scores and aggregate counts, including unknown overblocking |
| `core/attempts/` | Per-try bundles, manifests, grading and reset records. Resolve each CSV `evidence_path` relative to `core/`. |
| `core/snapshots/` | Shared H1 handoff evidence referenced by the ledger |
| `checkpoints/` and `budget.sqlite3` | Per-block checkpoints and the operator's accounting records |

From the original archive root, run `sha256sum frozen-plan.json core/run-ledger.json score.json` or use PowerShell `Get-FileHash -Algorithm SHA256 -LiteralPath 'frozen-plan.json','core/run-ledger.json','score.json'`. Compare the three file hashes with `frozen_plan_sha256`, `run_ledger_sha256` and `score_sha256` under `source_digests` in the [published snapshot](live/live-progress.json). Use the original bytes for this comparison.

To verify a row, match its ordinal and attempt key in the run ledger and score, then inspect the selected attempt's raw request, authorization decision and available receipt. For the unknown overblocking counts, consult `score.json` at `summary.overblocking.unknown_requests` and `summary.overblocking.unknown_benign_attempts`. The earlier CSV cannot recover those counts.
