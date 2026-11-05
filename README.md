# Privacy Boundaries in Agent Handoffs and Cloud Fallbacks

**智能体跨设备交接与云端回退的隐私边界** · DASE7508 Security of Intelligent Systems

[简体中文](#中文) · [English](#english) · [项目路线图 / Project roadmap][i27]

## 中文

### 研究问题与系统边界

一个会议助理从桌面切换到模拟手机，或在本地日程工具超时后改用恢复路径时，攻击者能否通过会议文档，诱导它发送超出当前任务授权的日历和联系人信息？正常任务需要解释公开议程，并返回最多三个可用时段。

实验在一台计算机上模拟桌面、手机和云端接收方。可信的本地工具根据合成日历计算时段。原始事件标题、地点和电话号码存储在本地，所选实验策略决定如何处理对外释放请求。计划中的托管模型和模拟云端接收方都位于本地信任边界之外。请求经过统一的出站适配器，分别记录模型提议、策略决定、实际序列化的请求，以及观察到的响应或回执。

攻击者只能修改一份会议文档的正文。实验程序控制用户请求、可信标签、授权规则和故障开关。交接摘要保留原始来源、消息角色和任务范围。模型或文档声称获得了授权时，程序仍以可信策略为准。完整系统的组件依赖以 [Issue #27][i27] 为准。

### 计划中的实验

| 维度 | 对照条件 |
| --- | --- |
| 交接 | **H0** 直接加载文档。**H1** 在桌面生成并保存摘要，再由模拟手机加载。同一用例、文档条件和重复轮次的摘要在各策略和故障条件间复用。 |
| 本地故障 | **F0** 主日程工具正常运行。**F1** 主工具超时，可信的最小时段恢复工具仍可使用。双工具失败另做补充实验。 |
| 释放策略 | **S0** 仅提供隐私指令并记录发送。**S1** 解析对象句柄后对出站值做固定模式脱敏。**S2** 使用静态对象与字段白名单。**S3** 保留上下文来源，在加载和每条出站路径检查任务、用途、接收方与可信派生关系。 |

拟采用 12 对合成文档，覆盖过度披露、伪造授权、跨任务复用、借故障要求回退四类攻击。每对文档只替换一个段落。完整方案计划做 **1,152 次核心尝试**和 **240 次补充尝试**，后者覆盖合法分享、跨任务持久化及双工具失败。团队先跑开发试验，再冻结模型、用例、参数、评分和预算。[开发试验][i21] · [协议冻结][i22] · [核心实验][i23] · [补充实验][i24]

判定披露时检查实际出站请求中的禁止字段，并结合可用的接收证据。模型提议、拦截和送达状态未知分别记录。任务效用按议程与时段的正确性、合法请求被拦截的情况评估，同时记录 API 错误、令牌、字节与延迟。[分析方案][i25]

### 当前可运行内容与复现

| 原型 | 位置与当前范围 |
| --- | --- |
| A 模块离线工作流 | `main` 上的 [`member_a/`](member_a/README.md)，由 [PR #4][p4] 合入。包含有步骤上限的代理循环、跨进程 H1 交接、任务隔离、发送记录和重置。 |
| T01 出站机制试验 | [PR #2][p2] 提供的 `agent_privacy/` 和 `fixtures/t01.json`。使用脚本控制器运行 H0/F0 下的良性与攻击文档 × S0/S3，共四个场景。 |

两个原型均使用 Python 3.11+、标准库和合成数据，可离线运行。托管模型接入、统一集成及正式实验分别由 [#9][i9]、[#11][i11]、[#20][i20]、[#23][i23] 和 [#24][i24] 跟踪。

**A 模块。** 从含 `member_a/` 的仓库根目录运行。默认演示跨进程加载 H1 摘要，并在主日程工具超时后通过 F1 恢复路径完成任务。输出位于 `member_a/runs/`，可查看 `validation.json` 和各场景的 `events.jsonl`。

```sh
cd member_a
python run_demo.py
python verify.py
```

**T01。** 重新从仓库根目录开始。当前 `main` 尚无 `agent_privacy/` 时，从 [PR #2][p2] 检出独立工作目录。已有该目录时，在仓库根目录执行最后两行。

```sh
git fetch origin refs/pull/2/head
git worktree add --detach ../dase7508-t01-preview FETCH_HEAD
cd ../dase7508-t01-preview
python -m unittest discover -s tests -v
python -m agent_privacy.pilot --output artifacts/t01-pilot.json
```

在 T01 输出中对照 `proposals`、`decisions`、`outgoing_requests` 和 `receiver_records`。脚本设置下，只有 S0 攻击场景的模拟接收方收到原始合成日历信息，四个场景均完成本地日程路径。此处验证的是本地机制，真实模型行为和正式攻击率留待集成后评估。

### 五位组员分工与 Issue

| 角色 | 组员 | 分工 | 主要任务 |
| --- | --- | --- | --- |
| A | 夏张宁 · XIA Zhangning | 代理/API 主循环、跨设备交接、任务与会话隔离、实际发送记录、试验重置。协调全链路集成。 | [#3][i3] · [#9][i9] · [#11][i11] · [#20][i20] |
| B | 夏立原 · XIA Liyuan | 本地日程与恢复、超时注入、批量运行、确定性评分及统计。 | [#10][i10] · [#12][i12] · [#19][i19] · [#21][i21] · [#25][i25] |
| C | 金展 · JIN Zhan | 匹配攻击文档与成功判据、S1 模式脱敏、攻击结果分析。担任小组联络人。 | [#13][i13] · [#17][i17] · [#22][i22] · [#25][i25] |
| D | 张玺龙 · ZHANG Xilong | 协调接口约定，负责可信注册表、上下文组装、统一出站、S2/S3 和允许或拒绝原因。 | [#5][i5] · [#7][i7] · [#8][i8] · [#14][i14] · [#15][i15] |
| E | 江函谕 · JIANG Hanyu | 合成数据与良性文档、答案与字段规则、补充用例、证据复核和报告整理。 | [#6][i6] · [#16][i16] · [#18][i18] · [#24][i24] · [#26][i26] |

依赖顺序为原型 [#1][i1]、[#3][i3] → 接口约定 [#5][i5] → 组件开发 [#6–#19][i27] → 集成、开发试验及协议冻结 [#20–#22][i27] → 正式实验、分析与报告 [#23–#26][i27]。以 [路线图 #27][i27] 的逐项依赖和各 Issue 的验收条件安排工作。提 PR 前先查已有 Issue，说明验证命令和观察结果，再由另一位组员审查。版本库可保存合成数据、配置和复现说明。API 密钥、真实日历或联系人、学号和本地生成的运行产物留在本地。

## English

### Research question and system boundary

Can an attacker who controls a meeting document induce an assistant to send calendar or contact data beyond the active task's authorization after a desktop-to-mobile handoff or a local scheduling timeout? The legitimate task is to explain the public agenda and return up to three feasible slots.

The testbed simulates the desktop, mobile runtime, and cloud receiver on one computer. Trusted local tools compute slots from synthetic calendars. The testbed stores raw event titles, locations, and phone numbers locally. The selected experimental policy governs requests to release them. The planned hosted model and the mock cloud receiver both sit outside the local trust boundary. A common outbound adapter records proposals, policy decisions, actual serialized requests, and observed responses or receipts separately.

The attacker can edit only the body of one meeting document. The harness controls the user request, trusted labels, authorization, and fault settings. Handoff summaries retain the original source, message role, and task scope. The runtime bases release decisions on trusted policy even when a document or model claims authorization. [Component dependencies and ownership][i27]

### Planned evaluation

| Dimension | Conditions |
| --- | --- |
| Handoff | **H0** loads the document directly. **H1** generates and saves a desktop summary, then loads it on the simulated mobile runtime. Each fixture, document condition, and repetition reuses the same summary across policy and fault conditions. |
| Local fault | **F0** runs the primary scheduler normally. **F1** times out the primary scheduler while the trusted minimal-slot recovery tool remains available. Both-scheduler failure is tested separately. |
| Release policy | **S0** provides privacy instructions and records sends. **S1** redacts fixed patterns from outbound values after handle resolution. **S2** uses a static object and field allowlist. **S3** preserves provenance and checks task, purpose, recipient, and trusted derivation at load time and on every outbound path. |

The plan calls for 12 matched synthetic document pairs covering excessive disclosure, forged authorization, cross-task reuse, and fallback pretexts. Each pair differs by one paragraph. The full design plans **1,152 core attempts** and **240 supplemental attempts** for lawful sharing, cross-task persistence, and failure of both schedulers. The team runs development pilots before freezing the model, cases, settings, scoring, and budget. [Development pilots][i21] · [Protocol freeze][i22] · [Core runs][i23] · [Supplements][i24]

The evaluation checks actual outbound requests for prohibited fields and uses receiver evidence where available. Proposed releases, denials, and unknown delivery outcomes are recorded separately. Utility covers correct agenda facts and feasible slots as well as legitimate requests blocked. The study also records API errors, tokens, bytes, and latency. [Analysis plan][i25]

### Runnable prototypes and reproduction

| Prototype | Location and scope |
| --- | --- |
| Member A offline workflow | [`member_a/`](member_a/README.md) on `main` via [PR #4][p4]. It includes the bounded agent loop, cross-process H1 handoff, task isolation, outbound audit, and reset. |
| T01 release mechanism pilot | `agent_privacy/` and `fixtures/t01.json` in [PR #2][p2]. A scripted controller runs four H0/F0 scenarios across benign and attacked documents and S0/S3. |

Both prototypes use Python 3.11+, the standard library, and synthetic data. They run offline. Hosted model work, joint integration, and formal evaluation are tracked in [#9][i9], [#11][i11], [#20][i20], [#23][i23], and [#24][i24].

**Member A.** From the root of a checkout containing `member_a/`, run the commands below. The default demo reloads an H1 summary across processes and uses F1 recovery after the primary scheduler times out. Find `validation.json` and the per-scenario `events.jsonl` files under `member_a/runs/`.

```sh
cd member_a
python run_demo.py
python verify.py
```

**T01.** Start again from the repository root. If `agent_privacy/` is absent on `main`, use a separate checkout from [PR #2][p2]. If `agent_privacy/` is already present, run the final two commands from the repository root.

```sh
git fetch origin refs/pull/2/head
git worktree add --detach ../dase7508-t01-preview FETCH_HEAD
cd ../dase7508-t01-preview
python -m unittest discover -s tests -v
python -m agent_privacy.pilot --output artifacts/t01-pilot.json
```

Compare `proposals`, `decisions`, `outgoing_requests`, and `receiver_records` in the T01 output. In these scripted scenarios, the mock receiver gets raw synthetic calendar data only in the attacked S0 case, and all four local scheduling paths complete. The traces validate local mechanisms. Hosted model behavior and formal attack rates remain part of the integrated evaluation.

### Team and issue ownership

| Role | Member | Responsibilities | Key issues |
| --- | --- | --- | --- |
| A | XIA Zhangning · 夏张宁 | Agent/API loop, handoff, task and session isolation, actual-send recording, and trial reset. Coordinates system integration. | [#3][i3] · [#9][i9] · [#11][i11] · [#20][i20] |
| B | XIA Liyuan · 夏立原 | Local scheduling and recovery, timeout injection, batch runs, deterministic scoring, and statistics. | [#10][i10] · [#12][i12] · [#19][i19] · [#21][i21] · [#25][i25] |
| C | JIN Zhan · 金展 | Matched attack documents and success criteria, S1 redaction, and attack outcome analysis. Team contact. | [#13][i13] · [#17][i17] · [#22][i22] · [#25][i25] |
| D | ZHANG Xilong · 张玺龙 | Coordinates interface contracts. Owns the trusted registry, context assembly, outbound mediation, S2/S3, and policy decision reasons. | [#5][i5] · [#7][i7] · [#8][i8] · [#14][i14] · [#15][i15] |
| E | JIANG Hanyu · 江函谕 | Synthetic data and benign documents, answer keys and field rules, supplemental cases, evidence audit, and report coordination. | [#6][i6] · [#16][i16] · [#18][i18] · [#24][i24] · [#26][i26] |

The sequence is prototypes [#1][i1] and [#3][i3], shared contracts [#5][i5], component work [#6–#19][i27], integration and protocol freeze [#20–#22][i27], then formal runs, analysis, and reporting [#23–#26][i27]. Follow the dependency table in [roadmap #27][i27] and each issue's acceptance criteria. Link the existing issue in each PR, record commands and observations, and have a different teammate review the changes. Commit synthetic data, configuration, and reproduction instructions. Keep API keys, real calendars or contacts, student IDs, and local run outputs out of commits.

[p2]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/2
[p4]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/4
[i1]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/1
[i3]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/3
[i5]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/5
[i6]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/6
[i7]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/7
[i8]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/8
[i9]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/9
[i10]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/10
[i11]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/11
[i12]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/12
[i13]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/13
[i14]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/14
[i15]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/15
[i16]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/16
[i17]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/17
[i18]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/18
[i19]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/19
[i20]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/20
[i21]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/21
[i22]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/22
[i23]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/23
[i24]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/24
[i25]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/25
[i26]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/26
[i27]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/27
