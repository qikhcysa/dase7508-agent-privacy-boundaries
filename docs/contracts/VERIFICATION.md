# Issue #5 验证记录

_2026-11-07；Codex 执行的开发检查，独立组员 review 尚待完成。_

---

## 📋 前置与范围

- 负责人：ZHANG Xilong / qikhcysa；主要 reviewer：XIA Zhangning / cynic004
- 开工前核对 Issue #5 与路线图 #27，唯一前置为 #1；其状态为 CLOSED，对应 PR #2 已合入 main
- 起始 main：`bc22edabaa121825d319768bfa9a17d511fab493`，其中包含 PR #2 的 `9f703f33b52b4aa021c3c6fc1064904a012ba33a`
- 独立分支：`issue-5-shared-contracts`；未修改旧原型运行时代码、旧 fixtures 或旧测试
- Git 直连 github.com:443 失败后，通过已授权的 GitHub API 读入本地缺失对象；每个对象按 Git SHA-1 校验，保持真实 main 提交身份后建立独立 worktree

## 🔍 已执行检查

环境：Windows，Python 3.11.5，jsonschema 4.19.2。使用合成数据，无托管模型或付费 API 调用。

| 命令或检查 | 实际结果 |
| --- | --- |
| `python -m contracts.validate` | attacked-h1.json、benign-h0.json 均为 VALID bundle |
| `python -m unittest discover -s tests -v` | 33 项通过：23 项新接口检查和 10 项已有 T01 检查 |
| `python -m agent_privacy.pilot --output artifacts/issue5-regression-t01.json` | 四个脚本场景均完成本地任务；仅 attacked/S0 收到原始合成日历 |
| Markdown 本地链接检查 | README 和接口说明中的本地链接均可解析 |
| 差异范围与空白检查 | 只提交接口、示例、校验器、测试、说明和依赖声明；提交前核对无空白错误 |

异常检查覆盖：空/缺省/重复/通配字段，模型夹带授权或故障开关，来源角色提升，缺失 user_id，H1 原始来源改写，错误用例/轮次摘要，作用域和用途替换，派生环、未知引用，错误日期/无时区/倒置区间，Base64/长度/哈希矛盾，接收字节不匹配，拒绝后的发送，缺失或失配的独立出站决定，HTTP 响应与模拟回执混淆，以及重复 JSON 键和 NaN。

同时确认合法的私有字段授权、S0 外发记录、S3 错误放行记录、超时未知送达和中断尝试仍能被表达。后两类安全效果由后续策略和评分任务判断，格式通过不等于防护有效。

## 📚 留存和未验证项

T01 回归输出保留在本地被忽略的 artifacts 目录，可用上表命令重新生成。contracts/examples 中的两份 JSON 是接口说明数据，不能当作这次回归的运行输出。没有重跑 Member A 的完整跨进程验证，因为本次未改变或接入其运行代码；两个原型到新接口的真实适配由各后续 Issue 完成。

没有验证托管模型、完整 H1/F1 集成、正式攻击率或正式实验预算。本次不运行 #6 的 fixture loader，也不完成 #7/#8 的 registry 或统一出站实现。

请 reviewer 从 PR 最新提交独立运行检查，核对字段约定和兼容映射，并记录实际命令、结果和未验证项。本文不是人工通过记录；agent 不批准、合并或关闭 #5。#6、#7 仍需等待 #5 合并和关闭。
