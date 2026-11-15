# 出站适配器

`agent_privacy.egress.EgressAdapter` 统一处理控制器请求和模拟云端释放。放行后记录交给传输层的确切 UTF-8 字节。决定、发送尝试、响应和模拟接收记录分别留存。

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

S0 使用隐私指令作为基线。有效的显式字段选择可以包含私有合成字段，用于测量指令本身对披露的影响。控制器接口接收非流式 Chat Completions 请求。

结构不合规的输入在发送前拒绝。v1 trace 可保存格式正确的提议。引用不存在的句柄或字段时，调用抛出错误，保留已记录的提议。写入发送记录失败时，传输层不会被调用。每个尝试使用新的 trace 文件，运行结束后可把事件列表装入 v1 bundle 验证引用、长度和哈希。

## S2 静态白名单

为 `run["policy"] == "S2"` 提供 `static_allowlist`。由可信运行时在启动前构造，并在采用相同规则的尝试中复用。以下为组件示例，正式规则随实验协议归档。

```python
from agent_privacy.egress import EgressAdapter
from agent_privacy.static_allowlist import StaticAllowlist

rules = StaticAllowlist({"document.meeting": ["text"], "schedule.slots": ["slots"]})
adapter = EgressAdapter(
    run, registry, controller=controller, trace_path=trace_path,
    static_allowlist=rules,
)
```

白名单逐一匹配句柄和明确列出的顶层字段，规则构造后保存为快照。每次发送检查本次消息及历史消息中携带的资产清单。可信运行时负责从登记的资产构造控制器消息并维护完整清单。模拟云端数据直接按提议选中的字段从注册表生成。

| 发送结果 | 原因代码 |
| --- | --- |
| 所选对象与字段全部在名单内，或请求不含资产 | `s2_allowlisted` |
| 句柄不在名单内 | `s2_object_not_allowlisted` |
| 句柄在名单内，但至少一个字段不在名单内 | `s2_field_not_allowlisted` |

任何一项超出白名单都会拒绝整次发送。拒绝记录候选载荷摘要和原因，随后抛出 `EgressDenied`。可用异常的 `send_id` 找到对应的 `egress_decision`。模拟云端还保留关联释放请求的 `policy_decision`。只有放行才会产生发送尝试。

正常与回退请求、控制器与模拟云端共用名单。规则只看句柄和字段，任务、用途、接收方、对象来源和派生链交由 S3 处理。S2 检查已登记的字段选择，名单内字段的内容可原样发出。

## 复现

从仓库根目录运行，使用 Python 3.11+ 和 `requirements-contracts.txt` 中的依赖。

```sh
python -m agent_privacy.egress_demo --output-dir artifacts/egress-s0
python -m contracts.validate artifacts/egress-s0/bundle.json
python -m unittest discover -s tests -p test_s2_allowlist.py -v
python -m unittest discover -s tests -v
```

S0 探针生成 `events.jsonl` 和 `bundle.json`。将 `send_attempt.body.base64` 解码后可查看提交给传输层的正文。模拟云端的 `receiver_record` 使用接收器记录的字节。脚本控制器响应标为 `scripted_response_observed`。HTTP 测试使用本机 127.0.0.1 模拟服务。S2 测试覆盖 F0/F1 两种出站输入、两个接收方的放行和拒绝、名单快照以及跨上下文的相同决定。所有验证使用合成数据。

## S3 contextual checks

Select `--policy S3` on the hosted development command with either fault setting.
The same flag works with a frozen H1 artifact supplied through `--handoff-path`.
Summary generation remains shared across conditions. Use the [hosted setup](../hosted/README.md)
for connection and fixture options.

S3 checks the active binding, object purpose and recipient before reading or
releasing a field. The trusted orchestrator supplies grants for specific handles,
fields, purposes and recipients. A private field requires both an eligible
recipient in its source metadata and an explicit grant. The default hosted
configuration grants no raw private fields.

H1 requires a verified same-task import of a desktop summary with a document
parent. The summary retains its original assistant role, untrusted integrity and
desktop scope in source metadata. It is assembled into controller history as
tool data. Original document text stays in the audit archive. Derived slots
require the expected trusted scheduler, the current task's calendar parent and
a minimal result containing only start/end pairs. Trusted F1 recovery may send
those slots to the controller or mock cloud.

The adapter rechecks the trusted runtime's asset selections for every controller
send, including retained tool results, and uses the same authorization policy for
mock-cloud releases. Controller payload assembly, registry ingestion and runtime
grants are part of the trusted code. S3 controls structured data access and egress
and cannot infer the provenance of an arbitrary string in a model response.

Load and release decisions carry stable reason codes. A rejected selection
produces neither a send attempt nor a receiver receipt. Exact outbound bytes are
retained for requests that reach the transport. Run the offline regression tests
with `python -m unittest discover -s tests -p test_s3_contextual.py -v`.
