# #23 与 #24 的报告来源及复查

2026-11-24 核对时，#33、#23、#24 均开放，PR #74 和 #76 均未合并。Issue 正文和 #27 的依赖表都列出 #23、#24。匿名查询原生依赖的 API 返回 404，原生关联待核。#27 的部分进度描述早于当前两份 PR，以固定提交及其证据作为本草稿的出处。[Issue #33](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/33) · [路线图 #27](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/27)

| 来源 | 实际参考提交 | 本草稿用途 |
| --- | --- | --- |
| `main` | `bb0d4dff0b2925db330b9cb020a63ecd72afffc2` | 本机运行基线。使用现有的 T01、运行器、判据、评分器和 #22 冻结协议 |
| #23 / PR #74，未合并 | `a89e7febe48d75f902af0b991973e5face1c675b` | 核心实验已保存汇总和修正后的标签口径 |
| #24 / PR #76，未合并 | `bdd2975fde76541c7c2af69c78d9e51a1c859aea` | 补充实验归档内的两份已保存汇总和运行方式说明 |

## 核心结果正文引用 #23

报告的核心结果表可从 `docs/evaluation/evidence/issue23/live/README.md` 和 `live-progress.json` 取数，引用时附上 PR #74 的固定提交及暂定状态。该汇总标为 `preliminary=false`，记录执行提交 `518864f7535613d29c527a4f36143280f963f269`。汇总声明源评分 SHA-256 为 `d4dee000ab12ffefcaf8155215a25960372e56601a0d33073aea2e6247910db9` 和协议 SHA-256 为 `996a654ebc6b0486015d767e856bffa3369401ad5dc5de90639eff9c4aba86f3`。[Issue #23](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/23) · [PR #74](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/74) · [固定汇总](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/tree/a89e7febe48d75f902af0b991973e5face1c675b/docs/evaluation/evidence/issue23/live)

| 报告指标 | 保存的 #23 汇总 |
| --- | --- |
| 核心覆盖 | 1,152/1,152 个计划条件，36/36 组 |
| 严格任务完成 | 1,071/1,152。仅按运行状态有 1,127 个 `completed`，其中 56 个未达到严格任务完成 |
| 运行错误 | 25/1,152，其中 18 次 `invalid_json`、7 次 `transport_error` |
| 目标披露 | 修正后的汇总中已确认和已出站但送达未确认的目标披露均为 0。1,152 条标为 `no_target_disclosure_observed`，同时有 7 次 `delivery_unknown`。保留送达未知标记 |
| 良性合法请求误拦截 | 0/2,381 个已计为合法的请求，以请求为分母 |

进入报告前，用最终账本核对计划覆盖、物理尝试与中断计数、选中结果、重置及 7 条送达未知对估计的影响。已保存汇总中的模型信息不足以核对服务端实际模型，需由实验负责人用获准访问的记录核实执行版本、配置与模型。在 #23 评论中，旧版导出器曾把目标披露列固定成零。复查最终导出器是否按 `confirmed_success` 和 `outbound_delivery_unconfirmed` 取值，以及修正后的汇总是否已随代码进入 `main`。[旧版分组计数审查](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/23#issuecomment-7109615929) · [标签修正提交](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/commit/a89e7febe48d75f902af0b991973e5face1c675b)

## 补充结果单列引用 #24

PR #76 保存了归档 `docs/evaluation/evidence/issue24/run24-flashx-exploratory-2026-11-24.tar.gz`。本草稿只参考归档中两份汇总 `run24-flashx/score.json`、`run24-flashx/final-report.txt`，以及 PR 的来源和运行方式说明。归档 SHA-256 为 `2dc9b19af03c835edfd5387223c7354134f2ae5fc8dc338734a5a451e1fa3674`。两个汇总文件的 SHA-256 依次是 `f620414d717e0259bd9e3c592e5b6ab12b1f59be4fce76c7b747219edc2cd920`、`55e70e7cfe9ab622784384ddca8eb3a83a41285fb915bf3122f9f884e73f2edd`。[Issue #24](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/24) · [PR #76](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/76) · [固定证据归档目录](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/tree/bdd2975fde76541c7c2af69c78d9e51a1c859aea/docs/evaluation/evidence/issue24)

两份汇总都记录 240 次尝试，分为合法分享 48 次、跨任务 48 对共 96 次、H1 压力 96 次。两份材料记录的禁止出站均为 0，跨任务保留上下文导入被拒绝均为 48 次。报告中对三组分别列出分母，跨任务以 48 对描述边界结果，H1 压力的 96 次从正常排期效用率中排除。以下数字先在草稿中并列保留，等待同一最终账本导出的统一口径。

| 指标 | `score.json` | `final-report.txt` |
| --- | ---: | ---: |
| 合法分享任务完成 | 37/48 | 42/48 |
| 合法分享观察到的授权释放 | 3/48 | 4/48 |
| 跨任务完成 | 75/96 | 92/96，第一项 44/48、第二项 48/48 |
| 跨任务授权释放记录 | 13 | 16 |
| H1 压力组观察到双超时 | 85/96 | 96/96 |
| H1 压力组错误 | 96/96 | 96/96 |
| 全部运行错误 | 128/240 | 106/240 |

PR 描述采用文本汇总的多项计数。须对齐运行 ID、评分器版本、输入与账本条目，明确双超时观察和终态错误的不同口径，并由负责人选定可追溯的最终汇总。`score.json` 的 1.8235 元是估算，PR 描述约为 2.1 元，实际账单仍待核对。合法分享报告应分开统计模型是否提议、策略是否允许以及实际发送和可用回执，江涵宇的接收端独立审计仍待记录。每条件一次且只覆盖这批样例，零观察不能外推为普遍零风险。

#22 冻结的是 `glm-5.3-flash` 和串行运行。PR #76 的并行增补保留串行基线并称不改冻结模型，归档则标为 exploratory，记录 `glm-5.3-flashx` 和 32 并发。当前把它作为探索性补充材料，等待协议负责人确认实际请求和返回模型、参数、四分片调度及其批准记录。[#22 冻结协议](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/blob/bb0d4dff0b2925db330b9cb020a63ecd72afffc2/docs/evaluation/ISSUE22_2026-11-23.md) · [#24 并行增补](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/blob/bdd2975fde76541c7c2af69c78d9e51a1c859aea/docs/evaluation/ISSUE24_PARALLEL_ADDENDUM_2026-11-24.md)

## 临时参考接口和正式提交前复查

两份 PR 共有 #23 执行提交 `518864f7535613d29c527a4f36143280f963f269`。固定头提交的 `git merge-tree --write-tree --name-only --messages refs/reference/pr74 refs/reference/pr76` 返回 0，树为 `9796fae4c506f19b740afaca134c8e0541723978`。这是文本兼容检查，两份 PR 仍为各自独立的参考。PR #76 缺少 #74 后续导出器修正及 `live/` 汇总。运行器层面有以下差异，兼容性留给合并后的实际检出验证。

| 位置 | 更新后的 `main` 需要核对 |
| --- | --- |
| `agent_privacy/hosted.py` 的 `run_agent` | PR #76 新增 `retained_context_records` 和 `recovery_timeout_message`。核对旧的单条 H0 调用及补充路径所用的关键字参数 |
| `agent_privacy/runner.py` 的 `run_plan` | PR #76 加入 `plan_validator`，以 `handoff_snapshot_key` 判定是否需要快照提供器，区分 `snapshot_evidence_role`。核对计划、账本和快照字段 |
| `agent_privacy/supplements.py`、`agent_privacy/outcomes.py` | PR #76 的 `retained_summary` 新增 `records`，补充判据有独立的 `grade_supplement_bundle`。核对核心判据仍由 `grade_bundle` 产生，补充评分按合入的专用入口解释 |
| `requirements-contracts.txt`、`scorer.py`、v1 schema | 固定参考提交相对草稿基线未改这些文件，复查合入版本实际依赖、评分列、未知值和证据绑定 |

1. 等待 #23、#24 都关闭。确认所需代码和归档已进入 `main`，并记录两份合入记录以及更新后的 `main` 完整 SHA。若采用 squash，按最终文件和变更核对交付。
2. 从更新后的 `main` 新建 LF 干净检出。检查依赖约束、T01 摘要、CLI、计划与账本字段、附加判据和评分列。按 [复现指南](README.md) 重跑同一良性样例，把新 SHA、命令、退出状态和结果随草稿更新。
3. 核对已合并的 #23 修正汇总与 #24 归档、摘要值和差异的处理结论，按最终证据更新正文。正式报告中分别保留核心、补充和开发演示的分母。
4. 江涵宇在独立目录按更新后的版本复跑并填写自己的记录，保留其评分表和未通过项。#33 保持开放，等待正式审查。
