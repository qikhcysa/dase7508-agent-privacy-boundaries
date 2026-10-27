# Privacy Boundaries in Agent Handoffs and Cloud Fallbacks

DASE7508 group project prototype. We study whether attacker-controlled meeting material can induce an assistant to release private calendar or contact data outside the active task's authorization, especially after handoff or local scheduling failure.

## Current status: T01 mechanism pilot

This repository currently contains a **deterministic, synthetic-data pilot** for [issue #1](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/1). It checks that a common release adapter records both proposed and actual mock-cloud payloads, and that an active-task policy can reject a forbidden release while allowing derived meeting slots. Its scripted proposal is **not evidence that a language model follows a prompt injection**. No hosted model, real cloud service, personal data, or paid API call is used in this stage.

From the repository root, run:

```shell
python -m unittest discover -s tests -v
python -m agent_privacy.pilot --output artifacts/t01-pilot.json
```

The second command writes four traces: benign/attacked documents under S0 and S3, all with direct document loading (H0) and a working local scheduler (F0). Check `proposals`, `decisions`, `outgoing_requests`, and `receiver_records` in the JSON. Only `outgoing_requests` plus matching receiver records count as transmitted data. The fixture uses visibly synthetic private values.

## Study boundary

The submitted proposal specifies S0–S3 policies, H0/H1 handoff, F0/F1 scheduler conditions, 12 paired fixtures, and a separately frozen formal evaluation. The current pilot implements only the S0/S3, H0/F0 mechanism slice. It does not produce attack-success rates or support claims about handoff, fallback, model behavior, or real deployments. See [the implementation roadmap](docs/ROADMAP.md) for the next independently reviewable tasks.

The local prototype keeps actual task authorization separate from document and model text. Fields have an original task, source, sensitivity and derivation record. Every intended outbound recipient must pass through the same recording adapter. Synthetic fixture data and raw pilot traces stay in this repository; do not commit real calendars, contacts, credentials, API keys, or student IDs.

## Collaboration

Open a scoped issue, implement on a branch, submit a PR with exact verification evidence and limitations, and ask a different teammate to review before merging. AI assistance and human checks should be described in the PR. Repository setup and contribution requirements are governed by the course project guidelines and GitHub collaboration manual.
