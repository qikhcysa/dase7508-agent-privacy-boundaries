# Hosted summary handoff

H1 has two stages: generate a document-only summary on the simulated desktop, then continue the same task in a fresh simulated mobile attempt. Both stages use the shared recorded egress adapter. The original Member A offline workflow remains independently runnable.

## Generate and continue

Use Python 3.11+ and install `requirements-contracts.txt`. Credentials and service configuration follow the [hosted agent instructions](README.md). These commands use the configured hosted service and can consume API balance:

```sh
python -m agent_privacy.handoff --cache-dir artifacts/handoff-cache --task-id meeting-demo
python -m agent_privacy.hosted --handoff-path artifacts/handoff-cache/<cache-key>/artifact.json --task-id meeting-demo --output-dir artifacts/mobile-attempt-1
python -m agent_privacy.hosted --handoff-path artifacts/handoff-cache/<cache-key>/artifact.json --task-id meeting-demo --fault F1 --output-dir artifacts/mobile-attempt-2
```

The first command prints the complete artifact path; use that path in the second command. Each command supports `--non-interactive`, `--base-url`, and `--model`. Without `--non-interactive`, the existing API key dialog is used. No key is saved. `--document-variant benign|attacked`, `--repetition`, `--user-id`, and `--task-id` identify the intended input. Continue with the same fixture, document variant, repetition and principal used for generation. Use `--fixture` for a different validated synthetic fixture.

The Python entry points are `agent_privacy.handoff.prepare_handoff(...)`, `load_handoff(...)`, and `agent_privacy.hosted.run_agent(..., handoff_path=...)`. An injected scripted or loopback transport is an engineering test, not a hosted-model observation.

## Frozen summaries and scope

The cache key binds the complete validated fixture, document variant, repetition, user, task, generation endpoint, model and summary settings. It excludes policy and fault conditions. A successful cache entry is verified and reused without another generation request. New generation settings or inputs create a distinct entry. Concurrent generation reserves the entry by creating its directory exclusively; a second caller fails if the first entry is incomplete. Failed and interrupted generations keep their evidence and are never silently retried. Investigate the failure before choosing a fresh development cache; formal retry rules belong to the frozen protocol.

The cache is trusted runtime storage. Hashes detect corruption and inconsistent artifacts; they do not authenticate files against someone who can rewrite the entire cache. The runtime verifies the original fixture, summary lineage, metadata, archived generation bytes and summary response before importing an artifact. A continuation may use a different controller model from the generator; both model configurations remain separately recorded.

The document retains `meeting_document`, role `tool`, untrusted integrity and its original desktop scope. The summary retains `model_summary`, role `assistant`, untrusted integrity and a derivation link to that document. Mobile import adds a same-user/task context binding without changing original metadata. The model reads the summary through an explicit `release` tool result, with `loaded_message_role: tool`; summary content cannot become a system instruction or authorization. The complete original document is retained only in audit artifacts and the audit bundle. The mobile registry holds a metadata-only provenance anchor with an `audit_only` marker for the document, preserving its handle and metadata for the summary derivation chain, but not its text. Even a controller that knows the original handle cannot release its text to either the controller or mock cloud under S0. This is an H1 input boundary, not an additional S0 privacy policy; H0 still loads the full document.

## Reset and evidence

Each continuation creates a fresh registry, session, trial, conversation, scheduler results and tool-call counters. Only the explicitly validated summary values and source metadata are imported into the mobile registry; complete frozen source records remain in audit evidence. Teardown removes the active context bindings, and `reset.json` records the result. Successful, incomplete and failed attempts retain their evidence. Output directories must be new, so previous audit files cannot be overwritten.

Generation saves `artifact.json`, `generation-bundle.json`, `generation-events.jsonl`, and `generation-result.json`. The artifact contains the exact summary text, immutable source records, generation reference, settings hash and evidence hashes. The trace retains actual outbound and response bytes, including model identifier and usage when returned. The generation request contains the public document and summary instructions; local private calendar and contacts are excluded.

Mobile evidence follows the [hosted attempt format](README.md#evidence-and-checks), with an H1 artifact reference in `bundle.json` and a `reset.json` record. Loading decisions precede `context_loaded` events, whose source metadata matches the original summary record. The exact summary is present in the registry and tool envelope. Load failures occur before model transmission. Evidence bytes are rechecked and copied before mobile registry creation. A changed, missing, or unreadable generation file, or a failed evidence copy, produces a denied `handoff-load.json`, a zero-binding `reset.json`, and a compact `result.json` with phase `handoff_load` and zero controller steps/tool calls. These preflight failures do not produce a run bundle or model trace. If the output directory itself cannot be written, filesystem failure may prevent audit files from being saved.

## Reproduction and limits

These tests use synthetic data and make no external model calls:

```sh
python -m unittest discover -s tests -p "test_handoff.py" -v
python -m unittest discover -s tests -p "test_hosted_h1.py" -v
python -m unittest discover -s tests
python -m contracts.validate
```

The tests include generation and continuation in separate processes, cache reuse, immutable desktop provenance, wrong inputs, corrupt evidence, malformed generation responses, failed generation without retries, and old-handle rejection after reset. Complete S0/H1/F0 and S0/H1/F1 attempts reuse the same frozen summary, including the common recovery scheduler from [#12](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/12). Existing S0/S1/S2 egress boundaries are also exercised under F0/F1 run metadata with that summary. These boundary probes do not establish complete S1/S2 hosted loops. S3 contextual policy and full condition integration remain [#15](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/15) and [#20](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/20).

No formal trials or attack-success rates follow from these engineering tests. Live hosted H1 behavior, agenda semantics, the full policy/fault matrix and the frozen protocol require separate validation.

