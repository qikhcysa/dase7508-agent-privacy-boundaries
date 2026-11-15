# Issue #12 F1 timeout and recovery verification — 2026-11-15

This is development evidence for Issue #12, not a formal experiment or an independent approval. The branch started from current `origin/main` after Issue #10 was closed and PR #55 was merged. The assigned human reviewer remains XIA Zhangning (`cynic004`).

## Implemented boundary

- `run_agent(..., fault="F0" | "F1")` accepts the fault only from trusted runtime configuration and records it in `run.fault`. The tool schema has no fault argument.
- F0 runs the verified primary scheduler. F1 makes the primary scheduling call return the stable `primary_timeout` result without producing slots.
- Recovery is accepted only in a later tool batch after the runtime has observed the F1 primary timeout. Premature recovery and primary-plus-recovery in one batch are rejected before proposals or tool effects.
- Both successful paths call the same `schedule_fixture` verifier and return only derived `start`/`end` slot fields. F1 recovery is labeled `minimal_scheduler` and retains the calendar derivation parent.
- Controller sends and optional mock-cloud releases remain on the shared `EgressAdapter`; paired tests verify release requests, release-channel sends and receiver receipts under both F0 and F1.

## Automated checks

Using Python 3.11 with the project contract dependencies:

```sh
python -m unittest tests.test_scheduler \
  tests.test_hosted.HostedTests.test_complete_loop_preserves_reasoning_manifest_and_usage \
  tests.test_hosted.HostedTests.test_f1_timeout_uses_common_recovery_and_preserves_completion \
  tests.test_hosted.HostedTests.test_f0_and_f1_share_setup_except_declared_fault \
  tests.test_hosted.HostedTests.test_f0_and_f1_offloads_use_the_common_egress_adapter \
  tests.test_hosted.HostedTests.test_full_batch_checked_before_any_tool_effect \
  tests.test_hosted.HostedTests.test_recovery_rejects_whole_batch_without_scheduling_effects \
  tests.test_hosted.HostedTests.test_f1_recovery_requires_timeout_in_an_earlier_batch \
  tests.test_hosted.HostedTests.test_rejects_duplicate_calls_unknown_handles_and_forged_authority \
  tests.test_hosted.HostedTests.test_truncated_and_fabricated_final_are_not_completed \
  tests.test_hosted.HostedTests.test_limits_and_fresh_attempts \
  tests.test_hosted.HostedTests.test_http_error_and_unknown_delivery_are_preserved_without_retries
```

Result: **19 targeted tests passed**. Full discovery ran 126 tests: **123 passed**, while the three existing real loopback-HTTP tests in `test_egress`, `test_hosted` and `test_s1` could not bind `127.0.0.1` in the restricted implementation sandbox (`PermissionError: Operation not permitted`). This environment limitation is not converted into a passing result. Contract examples validated, `compileall` passed and `git diff --check` passed. The assigned reviewer should rerun full discovery in a normal local environment.

No paid or real hosted-model call was made. No API key or private user data was used. No review approval, merge, Issue closure, formal run, or group submission was performed by this implementation work.
