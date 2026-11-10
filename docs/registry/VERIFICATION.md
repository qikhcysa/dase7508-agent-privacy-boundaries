# v1 注册表验证

开发验证于 2026-11-07 至 11-10 在 Windows、Python 3.11.5、jsonschema 4.19.2 下执行。验证提交为 `f394993`，基于共享接口合并提交 `d8300ad`。验证使用合成对象，范围为注册表组件、v1 示例和 T01 回归。Codex 协助实现、复现审查问题和执行开发检查。

初次审查发现导入记录的 `handle=null` 会被自动编号并写入。修复后，导入拒绝空值、缺失和格式错误的句柄，两张表均不会新增记录。新建对象的 `put(value, meta)` 保留自动编号。XIA Zhangning 批准修复后的提交，PR #45 于 2026-11-10 合入 main。[审查问题](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/45#pullrequestreview-5817886550) · [复审批准](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/pull/45#pullrequestreview-5837257259)

| 命令 | 修复后结果 |
| --- | --- |
| `python -m unittest discover -s tests -v` | 56 项通过，其中 23 项注册表、23 项接口和 10 项 T01 检查 |
| `python -m agent_privacy.registry_demo` | 错任务和错会话分别返回 `task_mismatch` 和 `session_mismatch`。文档标签不变，摘要原始范围与角色不变，新上下文绑定可读取 |
| `python -m contracts.validate` | 两份共享接口示例均通过 |
| `python -m agent_privacy.pilot --output artifacts/issue7-review-t01.json` | 四个脚本场景均完成本地任务，仅 attacked/S0 的模拟接收方收到原始合成日历 |

注册表检查覆盖五字段范围匹配、可信上下文绑定、来源和标签保持、非法字段与句柄、重复或并发插入、父链、持久化和清理。组件边界见[注册表使用说明](README.md)。
