# Issue 34 verification, 2026-11-17

Base: main 2f9ff0b541f01fb1b19e99e2066320f091c9efe1, tree 8a2b718e27b0cc41227d06cfa66035293b47aee3. The base tree is identical to the tested #17 delivery tree. The existing codex/issue17 ref and all unrelated local files were preserved; implementation uses codex/issue34.

Gate verified before implementation and again before publication:
* #8 CLOSED, completed; PR #46 merged to main, merge 6c2d4714af8acc98fbcfe8ca2934601f55ede918.
* #17 CLOSED, completed; PR #60 merged to main, merge 2f9ff0b541f01fb1b19e99e2066320f091c9efe1.
* Native blocked-by relationships, issue 34 and roadmap 27 all identify #8 and #17.
* Authenticated account jinzhan857-sketch matches owner JIN Zhan; assigned independent reviewer is ZHANG Xilong (qikhcysa). No existing issue34 branch or open PR was found.
* Current AGENTS.md, collaboration guide, README, issue, roadmap, v1 schema/validator, egress adapter and issue17 criteria were read.

Environment: Windows, Python 3.12.14 and jsonschema 4.26.0 in the existing local .venv17, installed against requirements-contracts.txt. No dependency changes.

Commands executed from repository root:
```powershell
.venv17/Scripts/python.exe -m unittest tests.test_outcomes tests.test_matched_attacks tests.test_benign_fixtures -v
.venv17/Scripts/python.exe -m contracts.validate
.venv17/Scripts/python.exe -m unittest discover -s tests -v
.venv17/Scripts/python.exe -m agent_privacy.outcomes docs/outcomes/examples/attacked/bundle.json --output .git/issue34-cli-output.json
git diff --check
```

Final observed results:
* Focused suite: 32 tests passed in 3.855 seconds. This includes 24 outcome tests plus the 8 matched/benign regression tests. All twelve target IDs are exercised.
* Contract examples: attacked-h1.json and benign-h0.json both VALID bundle.
* Full suite: 192 tests passed in 19.481 seconds.
* CLI attacked example output equals its committed expected outcome, with target_outcome confirmed_success.
* All four saved bundles regrade exactly to their saved outcomes. Benign, lawful and blocked examples report no_target_disclosure_observed; attacked reports confirmed_success.
* git diff --check: passed.

Negative checks include corrupt hashes/receipts/scope, duplicate receipt, changed fixture baseline, malformed private source layouts, duplicate/nonfinite payload JSON, missing results, unknown delivery, and duplicate top-level JSON input. The latter intentionally returns CLI exit code 2 and prints Unable to read a strict JSON bundle. Invalid evidence stays ungraded. Test harness development initially referenced the wrong contact handle and accidentally shared mutable fixture/registry values; both were corrected in the test builder before the final checks.

The examples are actual EgressAdapter traces generated with synthetic inputs and scripted/in-process transports. They demonstrate the grader, not model attack effectiveness. No model requests, paid calls or formal experiments were run. Original-value matching does not infer arbitrary encoded/transformed or paraphrased disclosures. Statistical aggregation, denominators and dynamic authorization-history capture remain outside this component.

AI implemented and executed these checks, prepared examples/docs and published the PR via the authorized GitHub connector. Local and remote code trees are checked for equality. JIN Zhan remains the accountable owner. Owner inspection and ZHANG Xilong's independent latest-commit review are pending; no human approval is claimed.
