# v1 注册表：来源与上下文隔离

_Issue #7 的实现与接入说明；负责人 ZHANG Xilong，主要 reviewer XIA Zhangning（cynic004）。_

---

## 📋 运行和接入

`agent_privacy.scoped_registry.ScopedRegistry` 为后续组件保存[共享 v1 格式](../contracts/README.md)的对象，并检测跨用户、跨任务、错误 trial/session/device 的读取。原始元数据和当前上下文绑定分开保存；显式绑定新上下文不会改写对象来源。

```sh
python -m pip install -r requirements-contracts.txt
python -m agent_privacy.registry_demo
python -m unittest discover -s tests -v
```

探针实际操作内存 SQLite，使用合成数据，不调用模型或网络。预期 `wrong_task` 为 `task_mismatch`、`wrong_session` 为 `session_mismatch`；文档标签保持 private/tool/untrusted；摘要绑定新上下文后仍保留原始 assistant 角色和原始 scope。输出属于组件检查，不是模型攻击成功率。

具体命令、实际结果和未验证项见[验证记录](VERIFICATION.md)。

```python
from agent_privacy.scoped_registry import ScopedRegistry

with ScopedRegistry("registry.sqlite3") as registry:
    # trusted_value / trusted_meta / active_scope 由可信运行程序提供。
    handle = registry.put(trusted_value, trusted_meta)
    status = registry.check_scope(handle, active_scope)
    record = registry.get(handle, active_scope)
```

此例说明调用位置；变量必须来自真实运行上下文，不能直接取自模型参数或攻击文本。两个旧原型保留原有接口，逐模块适配按各自 Issue 执行。

## 🔐 存储与身份边界

```mermaid
flowchart TB
    accTitle: Immutable Provenance Context Binding
    accDescr: 可信元数据和不可信内容分别存储，上下文读取检查独立绑定，绑定不重写来源。
    trusted_meta[可信程序提供 meta] --> ingest[可信 put 摄取]
    value[文档或模型内容 value] --> ingest
    ingest --> metadata[不可变原始元数据]
    ingest --> content[独立内容列]
    ingest --> binding[原始上下文绑定]
    binding --> read[按当前 scope 读取]
    metadata --> read
    content --> read
```

元数据由可信摄取程序显式提供，包含原始 user/task/session/trial/device、source、实际 message_role、confidentiality、integrity、用途、接收方标签、producer 和父对象句柄。`meta_json` 与 `value_json` 是不同列；程序不会把内容里的 `role`、`authorization` 或 `confidentiality` 合并为元数据。

对象插入后没有覆盖或修改标签的 API。重复句柄会报错；输入和读取结果都是独立 JSON 快照，修改返回值不能修改数据库。每个被选择字段继承该对象的可信元数据；v1 使用对象级标签。需要不同标签的数据应分成不同对象，不能靠内容里的“字段标签”降密。

普通 `get(handle, active_scope)` 要求该对象在完整五字段身份下有绑定。不存在绑定时，返回 `user_mismatch`、`task_mismatch`、`trial_mismatch`、`session_mismatch`、`device_mismatch` 或 `context_not_bound`。`check_scope` 提供同样诊断而不返回对象值。

句柄在一个 registry 内唯一。不同任务需要不同句柄命名空间或独立数据库；复用名字不能偷偷覆盖旧来源。新表以 `v1_registry_` 开头，即使与旧原型共用 SQLite 文件，也不会把缺少 v1 身份信息的旧记录自动导入。

### 来源与绑定是两件事

`meta.original_scope` 永远保留创建时的身份。可信导入程序可以调用 `bind_context`，把同一 user/task 的对象附着到新的 trial/session/device，并记录已核验的 artifact 引用。不同 user/task 不能这样绑定。

```python
status = registry.bind_context(
    summary_handle,
    active_scope,
    binding_ref="frozen_summary_01",
)
summary = registry.get(summary_handle, active_scope)
```

绑定引用由可信导入程序提供，不能采信摘要中的“授权”声明。相同引用的重复绑定是幂等的；已有导入引用不能被静默替换。对原始上下文的重复绑定保留原始绑定记录。

成功绑定只表示对象属于这个读取上下文，不是外发授权，也不表示其内容可信。`get` 返回的摘要原始角色仍为 assistant；后续 context_loaded 事件的当前 tool 角色由 #11/#15 的运行代码另行记录。#11 仍需核验冻结摘要的 fixture/variant/repetition、生成证据及完整父链。

## 🔧 API 与错误原因

| API | 用途 |
| --- | --- |
| `put(value, meta, handle=...)` | 可信摄取，插入对象及其原始绑定；可自动生成句柄 |
| `put_record(record)` | 插入一个规范的 handle/meta/value 记录；父对象需已存在 |
| `get(handle, active_scope)` | 完整五字段绑定匹配后，返回独立对象快照 |
| `select_fields(handle, fields, active_scope)` | 同样检查上下文，再取非空显式字段；保留原始元数据 |
| `check_scope(handle, active_scope)` | 返回 matches、reason、differences、原始/当前 scope 及绑定来源 |
| `inspect_record(handle)` | 可信程序专用的无范围检查读取，用于诊断和受控实验；禁止作为模型工具暴露 |
| `inspect_lineage(handle)` | 可信程序查看父链的元数据，不返回父对象内容 |
| `bind_context(handle, active_scope, binding_ref=...)` | 可信导入程序显式附着同 user/task 的上下文，不改来源 |
| `list_handles(active_scope)` | 只列出该完整上下文的句柄 |
| `unbind_context(active_scope)` | 可信清理，只移除该上下文绑定，保留其他绑定和来源记录 |

`RegistryError.reason` 为稳定代码；`RegistryScopeError` 另带独立的 status 快照，供 #8/#15 记录原因。错误不会回显对象内容。

| 原因 | 含义 |
| --- | --- |
| `invalid_metadata` | 标签、角色或来源组合违反已合并的 v1 格式 |
| `invalid_scope` / `invalid_selection` | 身份字段或字段选择格式无效 |
| `invalid_record` / `invalid_json` | 记录包裹错误，或存在非有限数值、循环、非 JSON 类型等 |
| `invalid_handle` / `unknown_handle` | 句柄格式无效，或没有该对象 |
| `duplicate_handle` | 已有句柄不能覆盖 |
| `missing_derivation_parent` / `self_derivation` | 父对象缺失或自引用 |
| `binding_reference_conflict` | 已有上下文导入引用不同，拒绝静默替换 |
| `unknown_field` | 选择了对象不存在的字段 |

事务保证单次对象与初始绑定一起写入，失败时回滚；并发同句柄插入只有一个成功。跨上下文绑定与删除也使用事务。批量 fixture 的整体验证和装载由 #6 负责，本 API 不实现 fixture loader。

## 📚 对后续模块的交接

| 后续任务 | 使用方式 |
| --- | --- |
| #6 / #7 | 复用现有 v1 schema。`contracts.validate` 新增 scope、selection 两个公开 kind，定义本身未改变 |
| #8 | 将句柄解析、当前范围诊断和来源记录接入统一出站；模型和云端都要记录实际决定及字节证据 |
| #9 / #11 | 按可信 active_scope 使用 registry，保持原始来源，并在核验真实 artifact 后显式绑定新上下文 |
| #14 | 静态白名单策略不要直接把 registry 的上下文诊断当作 S2 的决策规则 |
| #15 | 按所选策略检查当前授权、用途、接收方及完整父链，不能只看当前对象的一张派生标签 |

注册表负责保存并暴露事实。它允许保留含跨任务父对象的派生链，以便观察和判定问题；不会自行将其洗白或自动授权。可信程序的 `inspect_record` 使受控 S0 实验能记录错用事实，避免存储层暗中变成 S3 防护。S3 的实际加载/释放规则和两条出站路径仍由 #15/#8 实现。

这是同一可信 Python 进程中的组件 API，不是对恶意本机 Python/SQL 代码的沙箱或加密存储。拥有数据库写权限的主机代码属于信任边界；格式校验也不能证明自报 metadata 的来源真实。

本次不迁移两个旧代理运行循环，不实施 H1 摘要生成、会话恢复、正式评分或付费模型实验。#8/#14/#15 仍按所有前置 CLOSED 且成果在 main 的规则开工。独立 reviewer 应检查最新提交、重跑验证命令，并记录具体结果；不以 agent 自检替代组员 review。
