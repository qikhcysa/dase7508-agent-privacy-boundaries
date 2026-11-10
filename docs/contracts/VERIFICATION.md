# v1 共享接口验证

开发验证于 2026-11-07 在 Windows、Python 3.11.5、jsonschema 4.19.2 下执行。验证提交为 `bc9eba6`，基于 `bc22eda`。数据为合成数据，验证范围为接口格式、引用一致性和 T01 回归。Codex 协助实现和执行开发检查。XIA Zhangning 审查并批准该提交，PR #44 随后合入 main。[批准记录](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/44) · [合并提交](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/commit/d8300ad8a7dd9aae3c8da34050f27e7072b75f65)

| 命令 | 结果 |
| --- | --- |
| `python -m contracts.validate` | `attacked-h1.json`、`benign-h0.json` 均通过 |
| `python -m unittest discover -s tests -v` | 33 项通过，其中 23 项接口检查和 10 项 T01 检查 |
| `python -m agent_privacy.pilot --output artifacts/issue5-regression-t01.json` | 四个脚本场景均完成本地任务，仅 attacked/S0 的模拟接收方收到原始合成日历 |

接口检查覆盖无效字段选择、伪造授权、角色提升、缺失身份字段、H1 来源与用例不匹配、错误日期、派生环、未知引用、重复 JSON 键和 NaN。证据检查覆盖载荷长度与哈希、接收字节不一致、拒绝后的发送、缺失出站决定，以及 HTTP 响应、模拟回执和未知送达的区别。

回归输出可用表中命令重新生成。接口样例位于 [contracts/examples](../../contracts/examples/)。
