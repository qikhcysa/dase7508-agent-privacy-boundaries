# Privacy Boundaries in Agent Handoffs and Cloud Fallbacks

**智能体跨设备交接与云端回退的隐私边界** · DASE7508 Security of Intelligent Systems

[简体中文](#中文) · [English](#english) · [项目路线图 / Project roadmap][i27] · [协作流程 / Collaboration](docs/COLLABORATION.md)

[共享接口 / Shared contracts v1.0](docs/contracts/README.md) · [对象注册表 / Scoped registry](docs/registry/README.md)

## 中文

### 研究问题与系统边界

一个会议助理从桌面切换到模拟手机，或在本地日程工具超时后改用恢复路径时，攻击者能否通过会议文档，诱导它发送超出当前任务授权的日历和联系人信息？正常任务需要解释公开议程，并返回最多三个可用时段。

实验在一台计算机上模拟桌面、手机和云端接收方。本地工具根据合成日历计算时段，原始事件标题、地点和电话号码存储在本地。实验策略决定哪些数据可以发往托管模型或模拟云端。集成方案通过统一的出站适配器分别记录模型提议、策略决定、请求字节以及响应或回执。

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

| 组件 | 位置与用途 |
| --- | --- |
| A 模块离线工作流 | [`member_a/`](member_a/README.md) 包含有步骤上限的代理循环、跨进程 H1 交接、任务隔离、发送记录和重置。 |
| 本地排期与恢复 | `agent_privacy.scheduler` 对 1--3 个时段执行确定性排期和验证；primary/recovery 都只返回派生的 `slots`。 |
| T01 出站机制试验 | 使用 `fixtures/t01.json` 和脚本控制器，比较 H0/F0 下良性与攻击文档在 S0/S3 下的表现，共四个场景。 |
| 共享接口与注册表 | [接口校验](docs/contracts/README.md)检查 v1 数据格式和日志的一致性，[注册表演示](docs/registry/README.md)验证对象来源与上下文隔离。 |

两个原型均使用 Python 3.11+、标准库和合成数据，可离线运行。托管模型接入、统一集成及正式实验分别由 [#9][i9]、[#11][i11]、[#20][i20]、[#23][i23] 和 [#24][i24] 跟踪。

**A 模块。** 从含 `member_a/` 的仓库根目录运行。默认演示跨进程加载 H1 摘要，并在主日程工具超时后通过 F1 恢复路径完成任务。输出位于 `member_a/runs/`，可查看 `validation.json` 和各场景的 `events.jsonl`。

```sh
cd member_a
python run_demo.py
python verify.py
```

**T01。** 从 `main` 分支的仓库根目录运行。

```sh
python -m agent_privacy.scheduler --fixture fixtures/t01.json --mode primary
python -m agent_privacy.scheduler --fixture fixtures/t01.json --mode recovery
python -m agent_privacy.pilot --output artifacts/t01-pilot.json
```

在 T01 输出中对照 `proposals`、`decisions`、`outgoing_requests` 和 `receiver_records`。脚本设置下，只有 S0 攻击场景的模拟接收方收到原始合成日历信息，四个场景均完成本地日程路径。此处验证的是本地机制，真实模型行为和正式攻击率留待集成后评估。

### 五位组员分工与 Issue

| 角色 | 组员 | GitHub 用户名 | 分工 | 主要任务 |
| --- | --- | --- | --- | --- |
| A | 夏张宁 · XIA Zhangning | [cynic004](https://github.com/cynic004) | 代理/API 主循环、跨设备交接、任务与会话隔离、实际发送记录、试验重置、全链路集成和复现材料。 | [#3][i3] · [#9][i9] · [#11][i11] · [#20][i20] · [#33][i33] |
| B | 夏立原 · XIA Liyuan | [Sherlyn-Xia](https://github.com/Sherlyn-Xia) | 本地日程与恢复、超时注入、批量运行、任务效用评分、正式实验及统计。 | [#10][i10] · [#12][i12] · [#19][i19] · [#23][i23] · [#24][i24] · [#25][i25] |
| C | 金展 · JIN Zhan | [jinzhan857-sketch](https://github.com/jinzhan857-sketch) | 匹配攻击文档与成功判据、S1 模式脱敏、攻击结果判定、开发试验核对、协议冻结和攻击案例分析。担任小组联络人。 | [#13][i13] · [#17][i17] · [#21][i21] · [#22][i22] · [#31][i31] · [#34][i34] |
| D | 张玺龙 · ZHANG Xilong | [qikhcysa](https://github.com/qikhcysa) | 协调接口约定，负责可信注册表、上下文组装、统一出站、S2/S3 和允许或拒绝原因。 | [#5][i5] · [#7][i7] · [#8][i8] · [#14][i14] · [#15][i15] |
| E | 江函谕 · JIANG Hanyu | [unicjiang777](https://github.com/unicjiang777) | 合成数据与良性文档、答案与字段规则、补充用例、泄露与合法分享审计、报告和展示整理。 | [#6][i6] · [#16][i16] · [#18][i18] · [#26][i26] · [#32][i32] |

## English

### Research question and system boundary

Can an attacker who controls a meeting document induce an assistant to send calendar or contact data beyond the active task's authorization after a desktop-to-mobile handoff or a local scheduling timeout? The legitimate task is to explain the public agenda and return up to three feasible slots.

The testbed simulates the desktop, mobile runtime, and cloud receiver on one computer. Local tools compute slots from synthetic calendars. Raw event titles, locations, and phone numbers are stored locally. The experimental policy controls what may be sent to the hosted model or mock cloud. The integration design uses a shared outbound adapter to record model proposals, policy decisions, request bytes, and responses or receipts separately.

The attacker can edit only the body of one meeting document. The harness controls the user request, trusted labels, authorization, and fault settings. Handoff summaries retain the original source, message role, and task scope. The runtime bases release decisions on trusted policy even when a document or model claims authorization. [Component dependencies and ownership][i27]

### Planned evaluation

| Dimension | Conditions |
| --- | --- |
| Handoff | **H0** loads the document directly. **H1** generates and saves a desktop summary, then loads it on the simulated mobile runtime. Each fixture, document condition, and repetition reuses the same summary across policy and fault conditions. |
| Local fault | **F0** runs the primary scheduler normally. **F1** times out the primary scheduler while the trusted minimal-slot recovery tool remains available. Both-scheduler failure is tested separately. |
| Release policy | **S0** provides privacy instructions and records sends. **S1** redacts fixed patterns from outbound values after handle resolution. **S2** uses a static object and field allowlist. **S3** preserves provenance and checks task, purpose, recipient, and trusted derivation at load time and on every outbound path. |

The plan calls for 12 matched synthetic document pairs covering excessive disclosure, forged authorization, cross-task reuse, and fallback pretexts. Each pair differs by one paragraph. The full design plans **1,152 core attempts** and **240 supplemental attempts** for lawful sharing, cross-task persistence, and failure of both schedulers. The team runs development pilots before freezing the model, cases, settings, scoring, and budget. [Development pilots][i21] · [Protocol freeze][i22] · [Core runs][i23] · [Supplements][i24]

The evaluation checks actual outbound requests for prohibited fields and uses receiver evidence where available. Proposed releases, denials, and unknown delivery outcomes are recorded separately. Utility covers correct agenda facts and feasible slots as well as legitimate requests blocked. The study also records API errors, tokens, bytes, and latency. [Analysis plan][i25]

### Runnable components and reproduction

| Component | Location and scope |
| --- | --- |
| Member A offline workflow | [`member_a/`](member_a/README.md) includes the bounded agent loop, cross-process H1 handoff, task isolation, outbound audit, and reset. |
| Local scheduling and recovery | `agent_privacy.scheduler` deterministically schedules and verifies 1--3 slots; primary/recovery return only derived `slots`. |
| T01 release mechanism pilot | A scripted controller uses `fixtures/t01.json` to run four H0/F0 scenarios across benign and attacked documents and S0/S3. |
| Shared contracts and registry | [Contract checks](docs/contracts/README.md) validate v1 formats and trace consistency. The [registry demo](docs/registry/README.md) checks provenance and context isolation. |

Both prototypes use Python 3.11+, the standard library, and synthetic data. They run offline. Hosted model work, joint integration, and formal evaluation are tracked in [#9][i9], [#11][i11], [#20][i20], [#23][i23], and [#24][i24].

**Member A.** From the root of a checkout containing `member_a/`, run the commands below. The default demo reloads an H1 summary across processes and uses F1 recovery after the primary scheduler times out. Find `validation.json` and the per-scenario `events.jsonl` files under `member_a/runs/`.

```sh
cd member_a
python run_demo.py
python verify.py
```

**T01.** Run from the repository root on `main`.

```sh
python -m agent_privacy.scheduler --fixture fixtures/t01.json --mode primary
python -m agent_privacy.scheduler --fixture fixtures/t01.json --mode recovery
python -m agent_privacy.pilot --output artifacts/t01-pilot.json
```

Compare `proposals`, `decisions`, `outgoing_requests`, and `receiver_records` in the T01 output. In these scripted scenarios, the mock receiver gets raw synthetic calendar data only in the attacked S0 case, and all four local scheduling paths complete. The traces validate local mechanisms. Hosted model behavior and formal attack rates remain part of the integrated evaluation.

### Team and issue ownership

| Role | Member | GitHub username | Responsibilities | Key issues |
| --- | --- | --- | --- | --- |
| A | XIA Zhangning · 夏张宁 | [cynic004](https://github.com/cynic004) | Agent/API loop, handoff, task and session isolation, actual-send recording, trial reset, system integration, and reproduction package. | [#3][i3] · [#9][i9] · [#11][i11] · [#20][i20] · [#33][i33] |
| B | XIA Liyuan · 夏立原 | [Sherlyn-Xia](https://github.com/Sherlyn-Xia) | Local scheduling and recovery, timeout injection, batch runner, utility scoring, formal runs, and statistics. | [#10][i10] · [#12][i12] · [#19][i19] · [#23][i23] · [#24][i24] · [#25][i25] |
| C | JIN Zhan · 金展 | [jinzhan857-sketch](https://github.com/jinzhan857-sketch) | Matched attacks and success criteria, S1 redaction, outcome grading, pilot review, protocol freeze, and attack-case analysis. Team contact. | [#13][i13] · [#17][i17] · [#21][i21] · [#22][i22] · [#31][i31] · [#34][i34] |
| D | ZHANG Xilong · 张玺龙 | [qikhcysa](https://github.com/qikhcysa) | Interface contracts, trusted registry, context assembly, outbound mediation, S2/S3, and policy decision reasons. | [#5][i5] · [#7][i7] · [#8][i8] · [#14][i14] · [#15][i15] |
| E | JIANG Hanyu · 江函谕 | [unicjiang777](https://github.com/unicjiang777) | Synthetic data and benign documents, answer keys and field rules, supplements, exposure/lawful-sharing audit, and report/presentation coordination. | [#6][i6] · [#16][i16] · [#18][i18] · [#26][i26] · [#32][i32] |

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
[i31]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/31
[i32]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/32
[i33]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/33
[i34]: https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/34
