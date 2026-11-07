# Issue #7 验证记录

_2026-11-07；Codex 执行的组件开发检查，独立组员审查待完成。_

---

## 📋 前置与交付

- 负责人：ZHANG Xilong / qikhcysa；主要 reviewer：XIA Zhangning / cynic004
- 开工前核对 #7、路线图 #27 与原生 blocked-by，唯一前置 #5 已 CLOSED；PR #44 已合入 main
- 起始 main：`d8300ad8a7dd9aae3c8da34050f27e7072b75f65`，包含接口提交 `bc9eba6b1ef94f8260f3be7be01c314093382fea`
- 独立分支：`issue-7-scoped-registry`
- 交付：v1 注册表、实际组件探针、验收测试及 API/兼容说明；scope/selection 复用既有 v1 schema 定义，仅新增独立校验入口

## 🔍 实际执行结果

Windows，Python 3.11.5，jsonschema 4.19.2。数据为合成数据，没有模型或网络实验调用。

| 命令 | 结果 |
| --- | --- |
| `python -m unittest discover -s tests -v` | 54 项通过：21 项新注册表检查、23 项已有接口检查、10 项已有 T01 检查 |
| `python -m agent_privacy.registry_demo` | 错任务为 task_mismatch，错会话为 session_mismatch；文档保持 tool/private/untrusted；摘要保持 assistant，原始 scope 未改写，新上下文绑定成功 |
| `python -m contracts.validate` | 两份共享接口示例均为 VALID bundle |
| `python -m agent_privacy.pilot --output artifacts/issue7-regression-t01.json` | 四种场景均完成本地任务；仅 attacked/S0 收到原始合成日历 |

组件检查实际使用内存或临时文件 SQLite，覆盖输入/输出快照隔离、所有五字段错配、未绑定上下文、用户/任务间禁止绑定、导入引用不可静默替换、单上下文清理、重开数据库持久性、未知/重复句柄、缺失/自引用父对象、完整来源链、未知/隐式/通配字段、非 JSON 数据、恶意内容中的角色/标签声明，以及两个连接竞争同一句柄时只有一个插入成功。

初次新测试执行发现 Windows 临时文件清理时旧原型连接尚未关闭；已修正测试资源关闭顺序，并在完整 54 项测试中确认通过。没有改变旧原型的生产代码来规避这一问题。

## 📚 边界与人工交接

API 只供可信摄取和运行程序调用。测试证明本组件 API 内的身份检测和来源保持，不证明对任意恶意本机 Python/SQL 代码的隔离。元数据需要真实可信来源；格式检查本身不能认证一个自报来源。

put/get 不判定外发授权。跨任务父链保留供后续策略审计，可信 inspect_record 用于受控基线观察；#8 和 #15 仍负责每条实际出站路径的记录和策略。绑定新上下文的 artifact 核验、冻结摘要、会话恢复与整体验证仍由 #11 等后续任务完成。

未重跑 Member A 完整跨进程验证，因为本次没有迁移或修改其 runtime。未运行托管模型、正式实验、攻击率或付费 API；组件探针不能当作这些实验的证据。

请 cynic004 在独立目录检出 PR 最新提交，重跑上述命令，核对原因代码及与已合并 v1 格式的一致性，并记录实际 review。Agent 不自行批准、合并或关闭 #7；#8 仍等 #7 合并并关闭，#14 等 #8，#15 等 #7/#8/#11。
