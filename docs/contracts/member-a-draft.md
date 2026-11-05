# Member A input for the shared task, tool, and trace contract

**Review draft · XIA Zhangning · [Issue #5][task]**

The offline workflow from [PR #4][offline] already demonstrates source-preserving H1 save/reload, task-scoped state, validated tool calls, and separate outbound attempts and responses. This contribution proposes the fields those paths need from the shared contract. The [T01 pilot][pilot] uses a different fixture and release envelope, so the example below is a proposed mapping for review. ZHANG Xilong owns the final contract and closure of [#5][task]. The T01 prerequisite [#1][t01] remains open.

## What Member A can confirm now

| Boundary | Evidence from the offline module | Proposed shared contract |
| --- | --- | --- |
| Task and fixture | The harness supplies the request, synthetic asset handles and condition settings. The model receives scoped context. | A fixture identifies the paired document text, local asset handles, and expected results. Each attempt identifies its fixture, variant and S/H/F conditions. The runner supplies an opaque `user_id` and task, session, trial and device IDs. `user_id` is an addition to the current four-field A-module scope. |
| Trusted authorization and object metadata | The runtime rejects unexpected tool arguments. Object labels and lineage come from the registry. | Store authorization separately from document/model text. A grant identifies an object handle, fields, purpose and recipient under the active scope. Record source, actual original message role, original scope, confidentiality, integrity, producer and parent handles on each object. An object label or document statement does not grant release. |
| Local tools and release | A accepts `schedule(mode)`, `release(handle, fields, destination)`, `save_memory(content)` and `load_memory(handle)`. T01 uses `object_id` and `mock-cloud`. | The example uses `handle` and `mock_cloud`. Model arguments express requests. The harness resolves the active scope, effective recipient and purpose before policy evaluation. Scheduling mode selects a tool path, while the harness controls faults. A common boundary should handle both controller sends and cloud offloads. |
| H1 and reset | A stores summaries as untrusted assistant outputs with parents and generation traces. Mobile loads them as tool data. Ordinary attempts restore task state while preserving audit history. | Keep original and loaded roles distinct. Preserve the summary artifact ID, parent document, generation request and mode. Associate loading decisions with each attempt. Use the same immutable summary artifact per fixture, document condition and repetition across S/F settings, and apply each condition's load policy. |
| Run trace | A records tool proposals, decisions, exact request bytes before dispatch, and observed responses. T01 already separates proposals, decisions, outgoing requests and receiver records. | Join a proposal to a normalized request and a policy decision. Join transport attempts and responses by `send_id`. Keep exact body bytes, SHA-256, byte length, channel, and actual recipient. Record transport errors as unknown delivery. A mock receipt confirms mock reception. An HTTP response shows the provider response was observed. |

## Decisions for the team

1. **Empty field selection and naming.** A's offline `release(fields=[])` means the whole object. T01 rejects an empty list. The draft requires an explicit nonempty field list at the shared release boundary, even for S0, so malformed calls are handled consistently. Confirm the field-selection rule and the mapping from T01 `object_id`/`mock-cloud` to `handle`/`mock_cloud`. Owners of [#7][registry] and [#8][egress] can review this boundary.
2. **Attempt identity and H1 reuse.** Agree how to import the frozen summary artifact into separate attempts while retaining its original scope and generation record. The active attempt gets a fresh identity. Relabeling the original metadata would lose the evidence needed for cross-task checks. The existing A runtime tests same-task continuation, scripted reuse across reference policies, and isolated resets. Hosted summary reuse and cross-condition checks belong in [#11][handoff].
3. **Fixture and trace interfaces.** Confirm the fixture and answer-key fields with [#6][fixtures] and the runner/scorer in [#19][runner]. Confirm which identifiers, reasons, and evidence fields are required on all sends in [#8][egress]. Define the versioned event schema before the team writes shared loaders or scorers.

## Review example and validation

The [synthetic example](member-a-example.json) follows one scripted H1/S3/F1 attempt. It includes paired document text, active authorization, source metadata, the summary and its load decision, a rejected request for raw calendar events, and a permitted request for derived slots with matching illustrative send and receipt evidence. The generation send ID points to the preceding desktop trace, which the example omits. The [JSON Schema](member-a-draft.schema.json) checks this H1 release excerpt and rejects extra authority fields in model tool arguments. Other tools, provider response/error shapes, and the H0 schema still need agreement. Existing runtimes continue to emit their own formats.

Run from the repository root with Python and `jsonschema` available:

```sh
python -c "import json,sys; from jsonschema import Draft202012Validator as V; s,d=(json.load(open(p,encoding='utf-8')) for p in sys.argv[1:]); V.check_schema(s); V(s,format_checker=V.FORMAT_CHECKER).validate(d); print('Example matches draft schema')" docs/contracts/member-a-draft.schema.json docs/contracts/member-a-example.json
```

Schema validation checks structure. Trusted runtime code still owns authorization and source assignment, checks calendar ranges, verifies handle lineage and evidence joins, and checks serialized bytes against their digest. In the [offline tests][runtime-tests], an invalid model call is rejected before a valid call in the same batch can perform a side effect. The review draft does not complete the hosted H0/H1 work or the shared pipeline.

[task]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/5
[t01]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/1
[pilot]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/2
[offline]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/4
[fixtures]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/6
[registry]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/7
[egress]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/8
[handoff]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/11
[runner]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/19
[runtime-tests]: ../../member_a/tests/test_runtime.py
