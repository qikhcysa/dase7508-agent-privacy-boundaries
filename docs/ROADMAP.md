# Implementation roadmap from the submitted proposal

[Roadmap #27](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/27) tracks live progress, prerequisites, owners, and review assignments. The [shared board](https://github.com/users/qikhcysa/projects/1/views/2) shows current task status.

## Component deliveries

| Component | Owner | Merged work |
| --- | --- | --- |
| Hosted agent paths and H1 summary handoff | XIA Zhangning | [PR #54](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/54) · [PR #57](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/57) |
| Local scheduling, F1 recovery, batch runner, and utility scoring | XIA Liyuan | [PR #55](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/55) · [PR #56](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/56) · [PR #63](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/63) |
| S1 redaction, paired attack inputs, and outcome grading | JIN Zhan | [PR #50](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/50) · [PR #60](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/60) · [PR #61](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/61) |
| Shared contracts, isolated registry, recorded outbound requests, and S2/S3 checks | ZHANG Xilong | [PR #44](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/44) · [PR #45](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/45) · [PR #46](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/46) · [PR #49](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/49) · [PR #58](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/58) |
| Fixture validation, benign cases and answer keys, and supplemental controls | JIANG Hanyu | [PR #51](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/51) · [PR #59](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/59) · [PR #62](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/62) |

## Integration and evaluation

1. [#20](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/20) connects S0–S3, H0/H1, and F0/F1 in an end-to-end model path with a shared trace schema. The runner and scorer follow-up is tracked separately in [#64](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/64).
2. [#21](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/21) runs the development pilot and same-process identity controls after integration. Keep pilot data separate from formal rates.
3. [#22](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/22) freezes the model, generation settings, fixtures, grading, attempt and retry limits, and spending cap before formal trials.
4. [#23](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/23) and [#24](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/24) run the formal core and supplemental controls sequentially. Preserve all planned attempts and keep API failures, overblocking, and degraded outcomes visible.
5. [#25](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/25), [#31](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/31), [#32](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/32), and [#33](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/33) cover statistics, mechanism analysis, exposure audit, and clean-checkout reproduction. They feed the [final report and presentation #26](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/26).
