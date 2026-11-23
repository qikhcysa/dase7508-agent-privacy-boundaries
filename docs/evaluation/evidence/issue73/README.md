# Issue 73 证据包（开发期排除性证据）

本目录是 [Issue #73](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/73)
补充实验的聚合证据。**它不进入正式核心 1,152 次或正式补充 240 次的分母，不改变 #22 冻结协议、正式 fixtures、正式判据或 #23/#24 的正式结论。**

## 范围与执行

- 日期：2026-11-24（Asia/Shanghai）。
- 执行代码基线：`codex/issue23-live-results`（PR #74）head `a89e7fe`，加上只在本批启用的开发期 harness 扩展（默认关闭，见下）。
- 计划尝试：213 次；已记录：213 次。
- 逐尝试状态：{"completed": 194, "error": 19}。
- 模型（按臂）：`attack` = `glm-4.5-flash`，`benign` = `glm-4-flash`，`lawful` = `glm-4-flash`。
- 数据：`fixtures/issue73/` 的 7 个确定性合成 fixture；正式 fixtures 未修改。
- 预算：免费额度档模型，模型费用预计 0 元；token 数记录在逐尝试证据中。

## 条件计数

| 臂/策略 | 尝试数 |
| --- | ---: |
| `attack/N` | 18 |
| `attack/S0` | 18 |
| `attack/W1` | 18 |
| `attack/W2` | 18 |
| `attack/W2P` | 18 |
| `attack/W3` | 18 |
| `benign/S0` | 6 |
| `benign/S1` | 6 |
| `benign/S2` | 6 |
| `benign/S2P` | 6 |
| `benign/S3` | 6 |
| `lawful/S0` | 15 |
| `lawful/S1` | 15 |
| `lawful/S2` | 15 |
| `lawful/S2P` | 15 |
| `lawful/S3` | 15 |

## 本批启用的开发期扩展（正式默认全部关闭）

- `denial_behavior`: `abort`（正式默认）/ `continue`（本批）：策略拒绝返回工具错误结果并继续任务。
- `tool_error_continue`: 整批工具调用未通过运行时校验时返回工具错误给模型并继续；正式默认关闭。
- `tool_argument_error_continue`: 工具参数错误（如未知字段）返回工具错误给模型；本批仅合法/良性臂启用。
- `private_grants` / `s2_private_rules`: 可信授权与静态白名单的开发期配置，用于合法分享与 W2P/S2P 对照。
- `instructions_variant`: `frozen`（正式）/ `lawful_share`（合法臂）/ `no_privacy`（N 与 W 系列无指令控制）。
- `answer_repair_attempts=1`: 最终 JSON 格式提醒（不重复工具效果）。
- S1 在无 S0 前导消息时按偏移 0 引用运行时消息（W1 控制条件修正）；正式 S1 行为不变。

## 文件

| 文件 | 内容 |
| --- | --- |
| `plan.json` | 规范化后的 213 次计划（fixture 路径改为仓库相对路径） |
| `summary.json` | 运行器逐格聚合（n、完成、披露、拦截、合法送达等） |
| `attempts.csv` | 逐尝试派生数据（无私有值原文，仅布尔/路径名/耗时） |
| `analysis.json` | Wilson 区间、Fisher 检验、Bonferroni 决策、稳健性检查 |
| `analysis_tables.md` | 同样内容的可读 Markdown 表格 |
| `README.md` | 本说明与源码/输入 SHA256 |

原始 bundle、对话、逐请求字节与可能含敏感提示文本的文件保留在本地 gitignored `artifacts/`，未提交；仓库只保留聚合统计与派生 CSV，可按本节命令复现。

## 复现命令

```sh
python -m contracts.validate
python -m agent_privacy.issue73 check
python -m unittest tests.test_issue73 -v
python -m agent_privacy.issue73 run --workers 2 --retries 20 --non-interactive
python -m agent_privacy.issue73 report
python -m agent_privacy.issue73_analysis --evidence artifacts/issue73-ablation/evidence --out artifacts/issue73-ablation/analysis
```

`run` 使用环境变量 `ZAI_API_KEY` 或 `AGENT_API_KEY`（不写入仓库）；对账户级并发（1302）与平台过载（1305）做有限退避重试，重试次数记录在逐尝试记录中，不作为模型结果入分母。

## 源码与输入 SHA256（LF 规范化的执行时工作副本）

```json
{
  "agent_privacy\\hosted.py": "9a7a4edef25adeb85dab25695fbd971503665c5cf7dca98fe8fd0cec36c94178",
  "agent_privacy\\egress.py": "92c048fb663b2f241502f377af311117ef291a5da3c4cc843bb285e6c0e126df",
  "agent_privacy\\issue73.py": "fbd2cdac664ab8d82cf6f368916af9d31521824a38b75b832dafda6aa59b9668",
  "agent_privacy\\issue73_analysis.py": "85595e727b66b7ffd7d9c2ab083c29ab2e02512db5498a850346c414434134c8",
  "tests\\test_issue73.py": "9c3b9cdf6bb972c4cc22a222eb09c29603b30759f09147740c11d331f864aed6",
  "docs\\evaluation\\ISSUE73_2026-11-24.md": "ec58c3dacab4315b8a02e48ecbdf7d353f1649873a0074e28349e0bd9f2e865b",
  "fixtures\\issue73\\C_calendar.json": "809b5e311d19ccb45c69922a212d9d6bc196b70e862b52f6433b923fbec1dea8",
  "fixtures\\issue73\\C_phone.json": "31ba97f0efc8fa96a1249a033a005f0270ef5426bc5dee4b1b631d1ae0f02f05",
  "fixtures\\issue73\\C_phone_lawful.json": "5d64ce5858517be7b0e15573e25322b5a60053a5e3e55b74f4b54017f8bad48e",
  "fixtures\\issue73\\P_calendar.json": "21e3e1a2c137eb6a97b29877732e990649f1bc890bd5f22402d95eeb0a9e4e70",
  "fixtures\\issue73\\P_calendar_lawful.json": "4df4e184d19176404c9eabbf461ff2cbd403dcfd1ef4035e7ff7b4d91feafbc5",
  "fixtures\\issue73\\P_phone.json": "00b6b0967c9badfad2dac6878f9483a79f9f8e13aa7d8c2179521eb2ae94d24e",
  "fixtures\\issue73\\P_phone_lawful.json": "284b7d6ae3a156ae955efd156406f9ca1409634b3185b152d4e54135ef45bc4b"
}
```

