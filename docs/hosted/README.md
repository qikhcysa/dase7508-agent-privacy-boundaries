# Hosted benign H0 agent / 云端模型正常任务

Issue [#9](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/9) adds one development-only **benign/H0/F0/S0** path. It adapts the reviewed Member A bounded-loop design to the v1 fixture loader, five-field scoped registry and shared egress adapter. The original offline commands remain available.

## 启动

需要 Python 3.11+，以及 Python 的 Tkinter 桌面组件（Windows 官方 Python 安装一般已包含）。在仓库根目录安装已有接口依赖：

```sh
python -m pip install -r requirements-contracts.txt
python -m agent_privacy.hosted
```

Windows 也可以双击仓库根目录的 `run_hosted.cmd`。程序弹出 **API Key 输入窗口**；服务地址和模型已预设，无需填写配置文件。输入密钥并点击运行即可，取消会退出。窗口显示实际目标服务器，密钥只显示遮盖字符，不保存密钥。运行结果和证据目录显示在终端中。

默认模型是 `glm-5.3-flash`，标准 API 地址是 `https://open.bigmodel.cn/api/paas/v4/`。使用该服务对应账号的 API Key；赠送额度和付费余额由服务商账户规则处理。程序不检查或保证资源包余额，也不会自动充值、改用另一个账号或切换付费服务。一次尝试可能产生多次模型请求。

## Configuration and headless use

The normal desktop dialog asks only for an API key and displays the selected destination host (including any explicit port). The key remains in process memory and is passed only to the transport's Authorization header. It is excluded from repr, configuration artifacts, prompts and ordinary logs. No key file is required or read by the application.

For automation, set `AGENT_API_KEY` in the local environment (`ZAI_API_KEY` is a fallback only for HTTPS `open.bigmodel.cn` on the default port or port 443), then run:

```sh
python -m agent_privacy.hosted --non-interactive --check-config
python -m agent_privacy.hosted --non-interactive --output-dir artifacts/my-new-attempt
```

`--check-config` validates local settings without any API call. An output directory must be new; prior evidence is never overwritten. Without `--output-dir`, each attempt gets a unique directory under `artifacts/hosted-h0/`.

Advanced configuration accepts `AGENT_BASE_URL`, `AGENT_MODEL`, or explicit `--base-url` and `--model` arguments. A base URL or full `/chat/completions` endpoint is accepted. This is a nonstreaming Chat Completions client, not a universal adapter for arbitrary model APIs. Changed services/models need separate compatibility testing. A custom destination requires an explicit service-specific `AGENT_API_KEY` or a key entered in the dialog; it never inherits `ZAI_API_KEY`. These overrides do not change the default experiment model or destination. URL credentials, queries and fragments are rejected; remote services require HTTPS. Do not put a credential in a URL or model name.

Default bounds: 8 model requests, 16 tool calls, 8192 maximum output tokens per request, 120-second request timeout. They can be set with `--max-steps`, `--max-tool-calls`, `--max-tokens`, and `--timeout`. Bounds apply to an attempt, not an account spending cap. HTTP failures, timeouts and quota failures stop the attempt; there are no automatic retries or provider fallbacks. A timeout means delivery may be unknown.

GLM-5.3 requests use enabled thinking with `clear_thinking: false`, reasoning effort `high`, temperature 1 and top_p 0.95. Original assistant reasoning content, when returned, is replayed unchanged in tool history. Other model names use the common Chat Completions fields without GLM-specific options. See [GLM model documentation](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash) and [thinking/tool history requirements](https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode).

## What runs

1. Load and validate `fixtures/t01.json`; select only its benign document paragraph.
2. Trusted ingestion registers the document, calendar and contacts with fresh opaque handles and a fresh user/task/session/trial/device scope. Only the user request, instructions, tool schemas and handle catalog enter the initial model request.
3. The model requests document `text` through `release(handle, fields, recipient="controller")`. The returned tool envelope preserves the document's original untrusted metadata.
4. The model invokes `schedule(mode="primary")`. The existing local scheduler computes up to three feasible slots from local calendar data; the runtime registers their trusted derived object and records its calendar parent. Only slots are returned by this tool.
5. The model returns JSON with `agenda` and `slots`. Completion requires actual document loading, a scheduling call, valid final structure, and slots exactly matching the local tool. Agenda facts remain available for teammate semantic review; this is not the formal scorer from #19.

The model-facing tool set is only `schedule` and `release`, using the shared v1 argument names. Runtime scope, purpose and authorization cannot come from tool arguments. The complete tool batch is checked before any tool effect. Recovery mode is outside this task and is rejected during batch preflight, before any proposal is recorded or tool is executed. H1 memory/handoff, F1 injection, S1–S3 integration, formal experiment execution and automatic grading belong to later issues.

S0 is deliberately an instruction-only baseline. Structurally valid private releases are observable, not blocked by a new hidden defense. Every controller send uses `EgressAdapter.send_controller`; every mock-cloud send uses `release_to_cloud`. The runtime keeps explicit selections for assets still present in conversation history. The default benign task does not require a cloud upload.

## Evidence and checks

Each attempt saves:

| File | Contents |
| --- | --- |
| `run.json` | v1 development condition, identities, requested model and bounds |
| `events.jsonl` | Tool proposals, load/release decisions, payload-bound egress decisions, exact request/response byte evidence, token usage and final outcome |
| `conversation.json` | Runtime conversation and tool results; actual complete requests also remain in byte evidence |
| `bundle.json` | Self-contained fixture, trusted authorization, objects, derivation parents and trace |
| `result.json` | Agenda, slots, execution status, checks, provider model/usage fields and unknown costs |
| `manifest.json` | Source hashes captured before requests (UTF-8, CRLF normalized to LF), model options, endpoint and exact artifact hashes |

Observed token counts are normalized from provider `prompt_tokens` and `completion_tokens`. Unknown counts/costs remain null. Original usage, model identifiers, errors and truncated replies are preserved in response bytes. An HTTP response does not prove what the provider retained; mock-cloud receiver records are separate. Errors and incomplete attempts remain in the archive and are not silently retried or dropped.

```sh
python -m unittest discover -s tests -v
python -m contracts.validate
python -m contracts.validate artifacts/my-new-attempt/bundle.json
```

For the original Member A regressions, run `python verify.py` from `member_a/`. These tests use scripts or local HTTP servers; they do not consume hosted API credits. Live development evidence is listed in the dated verification record beside this document. Formal model/settings/budget selection still requires [#22](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/22).
