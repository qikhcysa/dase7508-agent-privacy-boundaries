# Issue #33 复现清单 · #23 归档核验草稿

2026-11-24（香港时间）｜负责人 夏张宁（`cynic004`）｜独立评审 JIANG Hanyu（`unicjiang777`）

当前范围是从固定 Git 提交取出 #23 的归档，核对版本、文件和计数。#33 的正式验收还需要 #23、#24 关闭且交付物进入 `main`，以及队友从干净 checkout 独立复现代表性运行和评分表。此草稿记录归档核验。 [Issue #33](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/33)

## 1. 固定版本

| 项目 | 固定标识 | 核对依据 |
| --- | --- | --- |
| 冻结方案 | `bb0d4dff0b2925db330b9cb020a63ecd72afffc2` | #22 方案进入 `main` 的提交。 [冻结方案](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/blob/bb0d4dff0b2925db330b9cb020a63ecd72afffc2/docs/evaluation/ISSUE22_2026-11-23.md) |
| #23 执行代码 | `518864f7535613d29c527a4f36143280f963f269` | 最终 JSON 的 `execution_commit`。 [执行提交](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/commit/518864f7535613d29c527a4f36143280f963f269) |
| #23 结果归档 | `169ec6a76412383f0bc3fe773b8948570ce58454` | `codex/issue23-live-results` 的最终结果提交。快照生成于 11 月 24 日 01:54:00（UTC+8），`preliminary=false`。 [归档提交](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/commit/169ec6a76412383f0bc3fe773b8948570ce58454) |

最终 JSON 记录的协议标识 `protocol_sha256` 为 `996a654ebc6b0486015d767e856bffa3369401ad5dc5de90639eff9c4aba86f3`。以下文件用固定归档提交定位，避免随分支更新而变化。

## 2. 结果文件

三个文件均位于 `docs/evaluation/evidence/issue23/live/`。Git blob ID 用于核对归档内容。

| 文件 | 用途 | Git blob ID |
| --- | --- | --- |
| [live-attempts.csv](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/blob/169ec6a76412383f0bc3fe773b8948570ce58454/docs/evaluation/evidence/issue23/live/live-attempts.csv) | 逐条记录，复算分母、任务完成数、运行错误、reset 与披露标签 | `9797cfdf2ed83991299e1a1271254c259eb39574` |
| [live-progress.json](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/blob/169ec6a76412383f0bc3fe773b8948570ce58454/docs/evaluation/evidence/issue23/live/live-progress.json) | 运行版本、总体汇总和来源摘要 | `25cd0c1c10236c4ba67d9d5f7cc42f7e04d6a098` |
| [README.md](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/blob/169ec6a76412383f0bc3fe773b8948570ce58454/docs/evaluation/evidence/issue23/live/README.md) | 人读摘要，便于报告引用与对账 | `2b8fd73325b7ed19fd97b4ccac37f770efcba2e2` |

正式复现包补齐时，将实际运行账本、评分文件和冻结计划的 SHA-256 逐一对照 JSON 中 `source_digests`。当前分支提供派生归档，这三项来源摘要还需要用原文件验证。

## 3. 归档核对项

- [x] **覆盖与分母。** 1,152 条记录，序号 1–1,152 连续，`attempt_key` 唯一。36 组各 32 条，S0–S3 各 288 条。
- [x] **运行状态。** `status=completed` 为 1,127 条，`status=error` 为 25 条。错误为 `invalid_json` 18 条和 `transport_error` 7 条。
- [x] **任务完成。** 按 `task_completed=True` 计 1,071/1,152（93.0%）。报告任务完成率时使用这一列。
- [x] **观察结果。** CSV 中 1,152 条 `target_outcome` 为 `no_target_disclosure_observed`。`privacy_labels` 中有 7 条 `delivery_unknown`，继续保留送达不确定性。分组和分策略的披露计数以逐条 CSV 复算为准，归档导出器的这两张表存在标签映射问题。 [导出器问题](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/23#issuecomment-7109615929)
- [x] **重置记录。** CSV 全部 1,152 条为 `reset_ok=True`。如需核对 H1 交接内容和 reset 的执行顺序，向负责人取得对应的脱敏证据。
- [ ] **独立复核。** 请评审记录核验日期、归档提交、脚本输出与任何差异。

## 4. 从固定归档复算

从本项目的本地 Git 仓库运行以下 PowerShell 命令，确认 `origin` 指向项目 GitHub 仓库。需要 Git 和 Python 3.10 以上。脚本只读取三个 Git blob 并核对元数据和 CSV 计数。

~~~powershell
git fetch --no-tags origin 169ec6a76412383f0bc3fe773b8948570ce58454
@'
from collections import Counter
import csv
import io
import json
import subprocess

revision = "169ec6a76412383f0bc3fe773b8948570ce58454"
directory = "docs/evaluation/evidence/issue23/live"
expected_blobs = {
    "live-attempts.csv": "9797cfdf2ed83991299e1a1271254c259eb39574",
    "live-progress.json": "25cd0c1c10236c4ba67d9d5f7cc42f7e04d6a098",
    "README.md": "2b8fd73325b7ed19fd97b4ccac37f770efcba2e2",
}

files = {}
for name, expected_blob in expected_blobs.items():
    source = f"{revision}:{directory}/{name}"
    blob = subprocess.check_output(["git", "rev-parse", source], text=True).strip()
    assert blob == expected_blob, (name, blob, expected_blob)
    files[name] = subprocess.check_output(["git", "cat-file", "blob", source])

summary = json.loads(files["live-progress.json"])
csv_stream = io.StringIO(files["live-attempts.csv"].decode("utf-8"), newline="")
attempts = list(csv.DictReader(csv_stream))
observed = summary["observed_summary"]

def count(column):
    return Counter(row[column] for row in attempts if row[column])

assert summary["execution_commit"] == "518864f7535613d29c527a4f36143280f963f269"
assert summary["protocol_sha256"] == "996a654ebc6b0486015d767e856bffa3369401ad5dc5de90639eff9c4aba86f3"
assert summary["preliminary"] is False
assert len(attempts) == summary["recorded_attempts"] == summary["planned_attempts"] == 1152
assert [int(row["ordinal"]) for row in attempts] == list(range(1, 1153))
assert len({row["attempt_key"] for row in attempts if row["attempt_key"]}) == 1152
groups = count("group")
assert len(groups) == summary["complete_blocks"] == summary["planned_blocks"] == 36
assert set(groups.values()) == {32}
assert groups == {row["group"]: row["recorded"] for row in summary["groups"]}
assert count("policy") == dict.fromkeys(("S0", "S1", "S2", "S3"), 288)
assert count("status") == observed["status_counts"] == {"completed": 1127, "error": 25}
assert count("task_completed") == {"True": observed["completed_attempts"], "False": 81}
assert observed["completed_attempts"] == 1071
assert count("error_type") == observed["error_type_counts"] == {"invalid_json": 18, "transport_error": 7}
assert count("target_outcome") == observed["target_outcome_counts"] == {"no_target_disclosure_observed": 1152}
assert count("privacy_labels") == observed["privacy_label_counts"] == {"delivery_unknown": 7}
assert count("reset_ok") == {"True": 1152}
print("OK: 3 Git blobs; 1152 unique attempts; 36 groups x 32; 4 policies x 288")
print("OK: 1071 completed tasks; 25 errors (18 invalid_json, 7 transport_error)")
print("OK: no target disclosure observed in archived rows; 7 delivery unknown; 1152 reset_ok")
'@ | python -
~~~

**本次核验记录（2026-11-24）** 已在临时 Git 仓库从远程按提交取回文件，用 Python 3.13.5 执行上述核验脚本，三个文件标识及所有断言均通过。Codex 整理此草稿并执行归档核验，独立评审待完成。

## 5. #24 结果发布后补齐

- [ ] 记录 #24 执行提交、结果提交、归档路径、文件标识和快照时间。
- [ ] 对照 #24 正式计划核对实际分母、区块覆盖、任务完成和错误。登记接收方证据的存放位置与访问方式。
- [ ] 两项前置交付进入 `main` 后，补齐 #33 的固定环境、运行清单、无密钥配置说明、合成数据来源、模型与 mock 的适用范围，以及预期输出。
- [ ] 由独立队友在干净 checkout 做代表性复现和评分表核对，归档实际输出、限制与评审结论。 [#24](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/24) · [#33](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/33)
