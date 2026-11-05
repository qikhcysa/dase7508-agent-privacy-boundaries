# Member A XIA ZHANGNING agent workflow

This standalone prototype provides the bounded agent loop, desktop-to-mobile handoff, task isolation, outbound request audit, and trial reset. The desktop process saves a scripted summary with source metadata in SQLite. A separate process reloads it as tool data and continues the meeting task. The runtime applies the selected policy before sending to the controller or mock receiver and records the serialized bytes and observed responses separately.

## Reproduce

Run these commands from the repository root with Python 3.11 or newer. The examples use the standard library and synthetic fixtures.

```shell
cd member_a
python run_demo.py
python verify.py
```

The default demo exercises S3/H1/F1: a separate process reloads the handoff and the local recovery scheduler returns three feasible slots after the primary scheduler times out. `verify.py` runs the regression tests and six cross-process scenarios. The commands create fresh directories under `runs/`. Check `validation.json` for test counts and source hashes, `demo_result.json` for scenario observations, and `events.jsonl` for proposals, policy decisions, serialized send attempts, and observed receipts. A `send_attempt` alone leaves delivery unconfirmed.

The controller and H1 summaries are scripted. The HTTP transport is exercised against loopback test servers. The sample scheduler and S0–S3 policies show the integration interfaces. Hosted model behavior, joint integration with the T01 pilot, and formal attack or defense results remain future work. See the [interface and acceptance notes](docs/接口与验收说明.md).
