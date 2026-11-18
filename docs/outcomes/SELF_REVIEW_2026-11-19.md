# PR 61 additional self-review, 2026-11-19

Reviewed parent: 8101588612ca7aa5fc4eb51f6442933d77aff0da. This is AI self-review, not independent human approval.

Findings and corrections:
1. The baseline digest was recomputed from the input dictionary's key order. Both normal runtime writers sort keys, so valid persisted B01-B12 bundles became ungraded. The grader now verifies the committed reference fixture against the existing issue17 digest and compares runtime fixture fields with that reference as JSON values. Object key order is irrelevant; changed data still fails. The attack paragraph exclusion and #17 format are unchanged.
2. Disclosure scanning ignored object keys. An original private title used as a JSON property name could reach the mock receiver while target_outcome reported no disclosure. Request-content scanning now covers both JSON keys and values, including escaped keys in embedded JSON, while role attribution continues to match actual record values rather than schema keys.
3. A verbatim generated summary can have the same text as its source document. A valid source envelope was previously exempted for only one matching object, causing a second same-text object to trigger a false promotion. An exact verified data-only envelope is now recognized at the message level. Raw content, privileged-role envelopes, altered source metadata and extra instructions retain the prior checks.

Independent offline probes against the parent reproduced findings 1 and 2: a sorted round-trip bundle was ungraded, and a received private key name was reported as no_target_disclosure_observed. New regression tests additionally use the actual run_agent and prepare_handoff writers, with a scripted model that returns a verbatim summary. All eight H0/H1, S0/S3, F0/F1 combinations complete normally and their persisted bundles grade without false promotion or target disclosure. This is a mechanism integration test, not evidence of real-model behavior.

Final verification, Windows Python 3.12.14 / jsonschema 4.26.0:
- .venv17/Scripts/python.exe -m unittest tests.test_outcomes -q: 31 tests passed in 6.147 seconds.
- .venv17/Scripts/python.exe -m contracts.validate: attacked-h1.json and benign-h0.json both VALID bundle.
- .venv17/Scripts/python.exe -m unittest discover -s tests -q: 199 tests passed in 21.641 seconds.
- git diff --cached --check: passed.
- Existing changed-fixture rejection, original review regressions, all twelve matched target cases and four committed outcome examples remain covered.

The expected negative JSON-input test prints an error message while passing. No real model, paid call, approval, merge or issue closure was performed. No compatibility layer or alternate fixture format was introduced. The latest commit still requires qikhcysa's independent review; self-review cannot guarantee the absence of all defects.
