# #21 开发试验与同进程身份对照

金展负责验收，夏立原操作真实模型并负责 Issue 指定审查，夏张宁逐轮核对重置。以下 96 次只用于开发，不计入正式统计。#18 和 #20 已关闭，成果分别经 PR #62 和 #68 合入 main。#20 的 16 次真实集成验证单独保留。

## 已批准的设计

提案《Privacy Boundaries in Agent Handoffs and Cloud Fallbacks》第 2 页规定 64 次开发试验和 32 次同进程身份对照，第 3 页列出项目总上限 500 元。金展于 2026 年 11 月 22 日确认本批的样本、对照和 5 元上限。

| 部分 | 输入与比较 | 本批尝试数 |
| --- | --- | ---: |
| 开发试验 | 两份专用合成会议，各有简洁版和含一段无关公开信息的版本。每个版本覆盖四种策略 × 两种交接条件 × 两种本地故障条件，各一次 | 64 |
| 身份对照 | 在一次 Python 进程中连续跑 16 对。每对先用原身份接续，再仅换用户或仅换任务。各 8 对，交替排列 | 32 |

开发试验用 `fixtures/development21/` 的四个文件。每份会议的两个版本使用相同议程、时段、联系人、日历和答案键，只有文件内的样本编号和一段公开背景不同。四个文件都走良性输入路径。每个版本用一份单独生成的 H1 摘要，在八个 H1 条件间复用。身份对照固定使用第一份会议简洁版的同一份摘要，策略 S3，H1，F0。每次有新的会话和尝试编号，原用户和任务从可信配置取得。原身份应成功加载，改变身份后应在加载阶段拒绝，控制器和工具调用均为零。合法加载与最终答案正确性分别记录。

## 夏立原的运行清单

从 GitHub 获取本次试跑的完整代码。在新的本地目录中执行以下命令，使用 Python 3.11 或更高版本。后续批次都在这一份副本中运行，以便共用账本。

```sh
git clone --branch codex/issue21 --single-branch https://github.com/qikhcysa/dase7508-agent-privacy-boundaries.git dase7508-issue21
cd dase7508-issue21
python -m pip install -r requirements-contracts.txt
```

1. 在同一台机器、同一份仓库副本中完成全部真实批次，先复核下方离线命令。运行 `python -m agent_privacy.issue21 plan` 生成排期，查看 `artifacts/issue21-operator/plan.json`。首份清单已经包含全部 96 个位置，正式统计始终排除该目录。
2. 使用本项目智谱账号的环境变量 `AGENT_API_KEY` 或 `ZAI_API_KEY`。仓库的配置自检可以在本机执行。`python -m agent_privacy.hosted --model glm-5.3-flash --base-url https://open.bigmodel.cn/api/paas/v4/ --non-interactive --check-config`。自检不发模型请求。批次固定使用同一服务、模型和 #20 的思考设置。不要把密钥写入记录。
3. 顺序运行下表。每项是一次独立启动，命令会保留每个尝试与失败。第一批结束后先核对本项目账单、失败与重置，填写下面的记录再继续。后续命令里的 `<累计实付元>` 替换为截至该批开始前 #21 的累计实际账单，不含 #20 和其他项目消费。已开跑的阶段会拒绝重复执行。

| 顺序 | 命令 | 尝试 |
| --- | --- | ---: |
| 1 | `python -m agent_privacy.issue21 D21M1Brief --bill-cny 0` | 16 |
| 2 | `python -m agent_privacy.issue21 D21M1Public --bill-cny <累计实付元>` | 16 |
| 3 | `python -m agent_privacy.issue21 D21M2Brief --bill-cny <累计实付元>` | 16 |
| 4 | `python -m agent_privacy.issue21 D21M2Public --bill-cny <累计实付元>` | 16 |
| 5 | `python -m agent_privacy.issue21 identity --bill-cny <累计实付元>` | 32 |

预算按 #20 的 49,602 个输入令牌、4,639 个输出令牌等比例外推。在智谱每百万输入 0.8 元、输出 2.8 元的价格下，如果 96 次都采用这 16 次的平均用量、输入均未命中缓存，约为 0.32 元。实际按服务商账单核对。5 元包括摘要生成、控制器请求和失败请求。每次发出请求前，`budget.sqlite3` 先按整个 1M 上下文和 8,192 个输出令牌保守预留约 0.86 元。取得用量后才释放多余预留。余额不足以覆盖下一次预留时停止发送。账单或用量不明、价格变化、重置不完整时暂停，保留目录与账本，由负责人核对后处理。费用按人民币记录，评分器中的 `cost_usd: null` 表示该字段未知。[智谱官方定价](https://docs.bigmodel.cn/cn/guide/start/pricing) · [#20 归档用量](../evaluation/evidence/issue20-live-t01.json)

4. 开发试验每块保留独立的 `plan.json`、`run-ledger.json`、每次的 `bundle.json`、`result.json`、`reset.json`、`outcome.json` 和 `score.json`。用 `python -m agent_privacy.scorer artifacts/issue21-operator/D21M1Brief --output artifacts/issue21-operator/rescore-first.json` 单独复算第一块。身份对照看 `identity/batch.json`、逐次目录和 `identity/observations.jsonl`。预期拒绝没有模型 bundle，保留加载、结果和重置文件。
5. 按每份快照比对原文、答案键和 `generation-result.json`，逐条记录保留、遗漏、新增或意义改变。记录 F0 主工具表现、F1 超时与恢复、非预期工具或 API 错误。误拦截用已授权请求作分母，把未知请求单列。失败和未执行的条件保留原编号，未经决定不补跑。按付款账单汇总当批和累计费用，摘要生成只计一次。若预算账本记录 `stopped_before_network`，可用请求体摘要对应本地记录，标为发送前停止。

## 夏张宁的重置清单

运行器发现未结算请求、发送前预算拦截或重置失败时，会保留当前证据并暂停。身份对照出现非预期决定也会暂停。中途暂停的阶段没有 `checkpoint.json`，下一阶段无法启动。将最后一次尝试的目录和报错交给金展核对，保留原目录及账本。

1. 按排期逐个核对，不用单个成功样例代表整批。每个正常启动的尝试检查 `run.json` 中的会话、尝试编号，确认本轮为新状态。核对 `reset.json`、`result.json` 和运行账本一致，绑定数归零、对话已清空且审计轨迹可读。H1 检查实际加载的摘要哈希。
2. 身份对照核对同一进程、同一快照、每对两个连续目录和唯一变化的身份字段。原身份在合法加载后可继续。变更身份时查 `handoff-load.json` 中的拒绝原因，确认未加载摘要、控制器和工具均为零、绑定为零。原身份已加载但后续排期失败时，身份结论、工具错误和任务效用要分别记录。
3. 给每个物理尝试登记本人核对记录、证据路径、结论和日期。遇到残留绑定、重复会话、缺失证据或无法解释的读取，保存该轮与前一轮目录并暂停后续批次。机器的 `reset_ok` 和脚本回放不能代替人工签核。

| 逐次记录字段 | 填写内容 |
| --- | --- |
| 批次与条件 | 开发或身份对照、样本版本、条件或配对号、物理尝试号、证据路径和版本 |
| 结果与异常 | 实际状态、任务完成、预期与实际加载决定、错误类型、工具路径、投递状态 |
| 摘要与误拦截 | 快照哈希、遗漏或新增的细节、已授权请求数、误拦截数和未知数 |
| 用量与费用 | 输入和输出令牌、缺失用量、独立摘要生成费、当批及累计人民币账单 |
| 重置与变更 | 清空状态、审计文件、人工核对人及日期、规则版本、改动理由与影响范围。无改动时明确写无 |

## 离线证据与验收

从仓库根目录安装 `requirements-contracts.txt` 中的依赖后运行。以下命令只使用脚本响应，每次使用新的证据目录。

```sh
python -m contracts.validate
python -m tests.issue21_preflight artifacts/issue21/checks-local
python -m tests.test_issue21 artifacts/issue21/rehearsal-local
python -m unittest discover -s tests -q
```

2026 年 11 月 22 日，在 main 提交 `8b88afc` 的基础上，AI 准备了开发样本、运行入口与交接说明，并用脚本实际回放。两项记录都排除在正式统计与真实模型批次之外。

| 证据 | 观测 |
| --- | --- |
| [已批准排期的整批回放](evidence/issue21/approved-rehearsal-20261122.json) | 64 个开发条件完成并重置，合法请求 288 个，脚本下误拦截 0 个。32 次身份对照符合预期。原身份 16 次可接续，只换用户与只换任务各 8 次在加载阶段被拒绝。 |
| [独立防护核验](evidence/issue21/offline-20261122.json) | 故意只给 H1 摘要保留三条议程中的一条，脚本仍可输出满分答案。分别换用户和任务均在零控制器请求时被拒绝。另一次模拟传输失败保留了未知送达、未知用量与重置证据。 |

2026 年 11 月 23 日，夏立原已跑完 64 次开发试验和 32 次身份对照，夏张宁已确认重置核对结果。四批开发记录的离线复算与提交的评分一致。真实运行的费用口径、逐份摘要偏差及核对方法见[验收记录](evidence/issue21/ACCEPTANCE_2026-11-23.md)。最新版本由夏立原独立审查。[Issue #21](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/21) · [项目路线图](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/27)
