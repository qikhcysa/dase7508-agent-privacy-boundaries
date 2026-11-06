# Implementation roadmap from the submitted proposal

The [T01 pilot issue](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/1) checks deterministic mechanics only. The full study must not infer model behavior or formal success rates from this scripted probe.

| Next work package | Proposal owner | Evidence needed before review |
| --- | --- | --- |
| Hosted agent loop, actual model/tool traces, H1 summary save/reload and reset | XIA Zhangning | Real generated summary text, prompts, tool proposals, and separated task snapshots |
| Local scheduler, F1 timeout, common legal recovery path, run automation | XIA Liyuan | Reproducible F0/F1 traces and a verifier for feasible slots |
| Three paired cases per attack family and S1 fixed-pattern redaction | JIN Zhan | Benign/attack pairs differing only in attack paragraph; explicit success criteria |
| S2 static allowlist and S3 task/purpose/recipient/provenance enforcement | ZHANG Xilong | Allowed and denied requests with exact policy reasons across normal and recovery paths |
| Synthetic assets, correct answers, lawful-sharing controls and audit | JIANG Hanyu | Fixture provenance, answer keys, no real personal data, manual audit notes |

After integration, run a small pilot and same-process identity controls; fix tool schemas and reset behavior. Freeze model identifier, generation settings, fixtures, grading, attempt limits, retry rule and spending cap **before** formal trials. The proposal plans 12 paired fixtures, S0–S3, H0/H1, F0/F1, three repetitions and separate supplements. Scale only after the first end-to-end real-model path works and the team verifies costs. Keep failed attacks, API errors, overblocking and degraded refusals visible.

Each issue should have a human owner and a different reviewer. PRs should link the issue, record exact commands and observations, identify AI assistance, and preserve limitations. Do not merge until a teammate verifies the latest changes.
