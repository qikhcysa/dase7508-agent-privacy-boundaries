# Privacy Boundaries in Agent Handoffs and Cloud Fallbacks

DASE7508 Security of Intelligent Systems group project. We study whether an attacker who controls a meeting document can cause an agent to send private calendar or contact data beyond the active task's authorization after a device handoff or a scheduling failure.

## How the system works

The planned harness simulates the desktop, mobile, and cloud receiver on one computer. A successful task explains the public agenda and returns up to three feasible slots.

1. The assistant reads a meeting document on the simulated desktop.
2. Local tools compute slots from a synthetic calendar. The controller sees meeting text, opaque handles, and permitted metadata. The runtime stores source, task, session, device, and derivation information in a trusted registry alongside local assets.
3. The simulated mobile process either loads the document directly or resumes from a saved summary. It can call a local recovery scheduler when the primary scheduler times out.
4. A common release adapter applies the selected policy to requests for the controller and mock cloud receiver. It records the policy decision, the exact serialized send attempt, and any observed receipt as separate events.

The attacker can edit one document body. The harness controls the user request, original labels, authorization, scheduler faults, and release adapter. The hosted controller in the planned study and the mock cloud receiver are outside the local privacy boundary. Raw event details, locations, and contact numbers stay local unless the task policy authorizes the specific release.

## Team and responsibilities

| Role | Member | Responsibility |
| --- | --- | --- |
| A | XIA Zhangning | Agent/API loop, desktop-to-mobile handoff, task and session isolation, actual-send recording, and trial reset. |
| B | XIA Liyuan | Local scheduling and recovery, fault injection, configuration switching, repeated runs, automated grading, and statistics. |
| C | Jin Zhan | Paired attack documents, attack goals and success criteria, S1 pattern redaction, and attack outcome analysis. |
| D | Zhang Xilong | Trusted policy, context and request assembly, outbound and fallback checks, and allow/deny reasons. |
| E | Jiang Hanyu | Benign documents and synthetic assets, expected answers and field rules, evidence review, case displays, and report layout. |

Jin Zhan is the team contact. The team shares integration, formal trials, interpretation, and writing. Each member reviews another component.

## Current prototypes and reproduction

Both prototypes use Python 3.11+ and synthetic data. Their documented checks run locally without API credentials.

### T01 release boundary pilot

The [T01 pilot](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/2) covers direct loading (H0), normal scheduling (F0), and S0/S3. It shows how the same scripted release proposal can reach the mock receiver under S0 and be denied under S3 while local scheduling completes.

From the repository root, run:

```shell
python -m unittest discover -s tests -v
python -m agent_privacy.pilot --output artifacts/t01-pilot.json
```

The second command writes four traces for benign and attacked documents under S0 and S3. Inspect `proposals`, `decisions`, `outgoing_requests`, and `receiver_records` in the JSON. A matching outgoing payload and receiver record establishes what reached the mock receiver.

### Member A handoff harness

Use a checkout containing `member_a/` from the [Member A PR](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/4). Its default demo exercises an H1 handoff across processes and a successful F1 recovery. The verifier runs the regression suite and writes traces to `member_a/runs/`.

```shell
cd member_a
python run_demo.py
python verify.py
```

The prototypes are independently runnable. Integration, hosted model validation, and formal evaluation are pending. The current traces establish local behavior under scripted decisions.

## Planned evaluation

The study compares S0 (privacy instructions), S1 (fixed-pattern redaction after handle resolution), S2 (static object and field allowlist), and S3 (source-preserving assembly and task, purpose, recipient, and derivation checks on loading and release, including fallback). Each condition records sends. H0 loads the document directly. H1 generates, saves, and reloads a summary. F0 runs the primary scheduler normally. F1 times out the primary scheduler while a trusted recovery tool remains available.

Twelve paired fixtures cover excessive disclosure, forged authorization, cross-task reuse, and fallback pretexts. Each pair keeps the legitimate task and assets constant. The attack paragraph is the only document difference. We plan to measure prohibited outbound disclosure, task completion, valid requests blocked, and costs in tokens, bytes, and latency. Supplemental tests cover lawful sharing, persistence across tasks, and failure of both local schedulers. The team will freeze the fixtures, model settings, and grading rules after the pilot. See the [implementation roadmap](docs/ROADMAP.md) and [dependency tracker](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/27).

## Collaboration

Open a scoped issue, implement on a branch, submit a PR with exact verification evidence and limitations, and ask a different teammate to review before merging. AI assistance and human checks should be described in the PR. Repository setup and contribution requirements are governed by the course project guidelines and GitHub collaboration manual.

Commit synthetic fixtures, configuration, and reproduction instructions. Keep local environment files, API credentials, generated raw traces, real calendars and contacts, and student IDs out of commits.
