# S0 出站适配器

Issue #8 把控制器请求和模拟云端释放接到 `agent_privacy.egress.EgressAdapter`。两条路径都先记录针对当前发送 ID 和载荷摘要的决定，再记录即将交给传输层的确切 UTF-8 字节。响应和模拟接收记录各有独立事件。

## 接入方式

每次尝试用经过校验的 v1 `run`、已装载的 `ScopedRegistry`、一个新 JSONL 路径和一个控制器传输实例构造适配器。脚本运行传 `ScriptedTransport`，托管运行传 `HttpTransport`。两个传输均复用 `member_a.agent_core.transport` 的底层实现。

| 入口 | 运行时职责 |
| --- | --- |
| `send_controller(payload, selections=[…])` | 构造可信 Chat Completions 请求并列出本次消息内所用资产的句柄与字段。历史消息仍含资产时也要登记。没有资产时显式传空列表。适配器在首条 system 消息中加入 S0 隐私指令。首次请求和含恢复结果的后续请求都调用此入口。 |
| `record_proposal(call_id, proposal)` | 解析控制器返回的工具调用后记录 v1 提议。提议中的额外字段会被拒绝。运行时生成或检查调用 ID，保持其在尝试内唯一。 |
| `release_to_cloud(call_id)` | 对已记录的 `mock_cloud` 提议取出明确指定的顶层字段。当前范围与用途由 run 绑定。相同调用只处理一次。 |

控制器工具结果放回后续消息，再调用 `send_controller`。适配器使用运行时提供的字段清单，检查句柄和字段存在。运行时负责从已登记资产构造消息和保留清单的完整性。模拟云端载荷则由适配器直接从注册表构造。

调用返回带状态和原始字节的 `TransportResponse`。运行时在解析成功响应前检查状态。HTTP 错误响应仍保存原始字节。传输异常会留下 `delivery_unknown` 并抛出异常。底层传输每次只发一个 POST，不自动重试或跟随重定向。认证参数只传给底层传输，发送记录保存请求正文和配置的无凭据 endpoint。

## S0 的边界

S0 使用隐私指令作为基线。有效的显式字段选择可以包含私有合成字段，即使当前任务没有授权释放。这个行为用于测量指令本身是否足够。S1–S3 策略、真实模型编排与 F1 故障注入分别由后续 Issue 负责。两个历史原型仍可按原命令复现。新接口目前接收非流式 Chat Completions 请求。

结构不合规的输入在发送前拒绝。v1 trace 可保存格式正确的提议。引用不存在的句柄或字段时，调用抛出错误，保留已记录的提议。写入发送记录失败时，传输层不会被调用。每个尝试使用新的 trace 文件，运行结束后可把事件列表装入 v1 bundle 验证引用、长度和哈希。

## 复现

从仓库根目录运行，使用 Python 3.11+ 和 `requirements-contracts.txt` 中的依赖。

```sh
python -m agent_privacy.egress_demo --output-dir artifacts/egress-s0
python -m contracts.validate artifacts/egress-s0/bundle.json
python -m unittest discover -s tests -v
```

探针生成 `events.jsonl` 和 `bundle.json`。将 `send_attempt.body.base64` 解码后可查看实际提交给传输层的正文。模拟云端的 `receiver_record` 使用接收器记录的字节。脚本控制器响应标为 `scripted_response_observed`。HTTP 测试使用本机 127.0.0.1 模拟服务，对比接收端读到的字节和发送前落盘的记录。测试覆盖 F0/F1 两种出站输入、合成私有标记、审计失败、无效字段、重复调用和未知送达。探针及测试的付费模型调用均为零。
