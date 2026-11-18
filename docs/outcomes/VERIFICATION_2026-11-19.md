# PR 61 review fixes, 2026-11-19

Parent reviewed commit: ed7d17d8232eb3aa035ccecbab4afa3ac114aa00, codex/issue34. Main remained 2f9ff0b541f01fb1b19e99e2066320f091c9efe1. Prerequisites #8 and #17 were rechecked CLOSED before changes. The local working tree was clean and the task branch matched the PR head. No #62 files were modified.

Review by qikhcysa:
- P1, discussion_r4610350082: a matching runtime grant must not override the source object's permitted recipients or purpose.
- P2, discussion_r4610350095: the normal H1 summary-generation user message is an explicitly untrusted data envelope, not role promotion.

Changes:
- _authorized now requires source metadata purpose and permitted recipient to agree with the active run/destination, as well as the current grant and original user/task.
- Role attribution recognizes the existing handoff generator's exact user-message envelope: only untrusted_document and source_metadata keys, with the full value and source metadata matching the registered untrusted object. A system/developer envelope, altered metadata/value, extra instructions or raw user-role content does not qualify.
- Four regression test methods cover both metadata conflicts, an actual benign prepare_handoff generation bundle, raw content in system/developer/user roles, and six envelope variants. No compatibility formats, runtime changes, model calls or policy changes were introduced.

Reproduction before the source fix:
```powershell
.venv17/Scripts/python.exe -m unittest tests.test_outcomes.OutcomeTests.test_source_restrictions_also_apply_to_matching_grants tests.test_outcomes.OutcomeTests.test_existing_benign_h1_generation_preserves_untrusted_envelope tests.test_outcomes.OutcomeTests.test_envelope_recognition_requires_user_role_and_exact_source -v
```
Observed: 3 test methods, 4 failing assertions/subcases, demonstrating the two source-metadata conflicts and the two normal-envelope misclassifications.

Final checks on Windows, Python 3.12.14, jsonschema 4.26.0:
```powershell
.venv17/Scripts/python.exe -m unittest tests.test_outcomes -v
.venv17/Scripts/python.exe -m contracts.validate
.venv17/Scripts/python.exe -m unittest discover -s tests -q
git diff --cached --check
```
- Outcome suite: 28 tests passed in 4.450 seconds.
- Shared examples: attacked-h1.json and benign-h0.json both VALID bundle.
- Full suite: 196 tests passed in 19.719 seconds.
- Expected negative CLI test prints Unable to read a strict JSON bundle; the suite is successful.
- Staged diff whitespace check passed. Existing four saved bundle/outcome pairs still match exactly.

AI implemented and ran these checks under JIN Zhan's authorization. All data/transports were synthetic/offline; no paid or real-model calls. qikhcysa's independent review of the new commit is requested. This document does not claim new human approval. Prior limitations on original-value matching, trusted input manifests and unlogged authorization changes still apply.
