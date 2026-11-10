# GitHub 任务组织与日常用法

任务状态见[共享看板](https://github.com/users/qikhcysa/projects/1)，负责人和前置依赖见[路线图 #27](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/issues/27)。开工与合并按[协作指南](COLLABORATION.md)执行。

看板用于跟踪状态。开工前核对原生依赖、Issue 正文和 #27，确认全部前置已关闭且成果已合入 main。

## 直接使用的五个视图

| 视图 | 看什么、怎么用 |
| --- | --- |
| [全部任务 / All tasks](https://github.com/users/qikhcysa/projects/1/views/1) | 全部任务、负责人、状态、Milestone、Labels、父任务和关联 PR。包含总览 #27。 |
| [任务看板 / Board](https://github.com/users/qikhcysa/projects/1/views/2) | 按 Todo、In Progress、In review、Done 分列。具体 Issue 上的 Blocked 标记提示原生依赖阻塞。 |
| [我的任务 / My work](https://github.com/users/qikhcysa/projects/1/views/3) | 使用 assignee:@me 显示当前登录组员负责的未关闭任务。每人使用自己的账号打开同一个链接。 |
| [待审查 / Review](https://github.com/users/qikhcysa/projects/1/views/4) | 状态为 In review 的工作。负责人在验证并准备好 PR 后更新此状态，reviewer 记录实际检查。 |
| [阶段总览 / Phases](https://github.com/users/qikhcysa/projects/1/views/5) | 按 Milestone 分组，查看各阶段的交付与负责人。 |

共享 Project 的视图对全组可见。GitHub Issues 侧栏里的 Views 是各账号自己的保存筛选，两者不是同一处配置。若需要个人快捷入口，可在 Issues → Views 新建视图，保存查询：

```text
repo:qikhcysa/dase7508-agent-privacy-boundaries is:issue is:open assignee:@me
```

## 原生关系分别表示什么

- **Parent / Sub-issues**：#27 是总任务，具体工作作为子任务列在其下，展示整体进度。父子关系表示归属，不表示必须先把 #27 关闭；#27 应保留到整个项目完成。
- **Blocked by / Blocking**：表示执行先后。例如 #5 被 #1 阻塞；从 #1 看，它 blocking #5。前置关闭后，GitHub 会反映新的阻塞状态，组员仍需核对 main 中的实际交付。
- **Relates to**：关联相关任务，不改变前置条件。
- **Security alert**：关联 GitHub 已有的仓库安全告警。

这些原生关系帮助发现阻塞；它们不会禁止人在本地编辑代码或创建分支。组员和 agent 必须执行协作手册中的开工检查。

## 标签与阶段

[Labels](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/labels) 用两类标签交叉分类：

| 类别 | 已配置的标签 |
| --- | --- |
| 工作性质 | kind:implementation、kind:data、kind:experiment、kind:analysis、kind:documentation、kind:tracking |
| 组件范围 | area:agent、area:scheduling、area:policy、area:data、area:evaluation、area:collaboration |

例如 #15 属于 implementation + policy，#17 属于 data + data。阶段使用 [Milestones](https://github.com/qikhcysa/dase7508-agent-privacy-boundaries/milestones) 表示，不再重复贴阶段标签：

| Milestone | 内容 |
| --- | --- |
| 00 Collaboration setup | 组员信息、协作规则和仓库组织。 |
| 01 Foundations and contracts | 基础原型、接口、可信登记、出站边界和排期。 |
| 02 Components and paired cases | 模型、交接/故障、防护、场景、运行及判定工具。 |
| 03 Integration pilot and freeze | 集成、开发试跑、规则与预算冻结。 |
| 04 Formal evaluation | 冻结后的核心与补充实验。 |
| 05 Analysis and delivery | 统计、案例、审计、复现、报告与展示。 |

阶段用于查看进度。截止日期以 Moodle 为准。

## 一位组员每天怎么用

1. 打开“我的任务”，进入一条任务，读正文验收标准和 Relationships。所有前置 CLOSED 且成果在 main 后，才把它移到 In Progress 并开始独立分支。
2. 实施、验证、保存证据，按协作手册提交 PR。未完成可用 Draft；完成负责人核对并准备组员审查后，改为 In review，留下 PR 链接。
3. 另一位组员检查最新提交，按意见修正后再合并。确认成果在 main、Issue 已关闭，项目的 Item closed 流程会将它移到 Done。
4. 更新 #27 复选框和必要的接口交接。下游负责人重新核对全部前置，不把上游的“已发 PR”当作完成。

Todo 中可以同时存在被阻塞和已就绪的任务；Todo 不等于可以立即开工。In review 是展示状态，实际审查依据是 GitHub PR 中的 review 和验证记录。

子任务自动加入看板，Issue 关闭后移至 Done。拖动看板卡片只更新展示状态。交付完成后按协作流程关闭 Issue。

## 新任务如何纳入

先检查是否已有对应 Issue。确需新增时，写清单一主负责人、不同 reviewer、验收标准，以及全部前置；独立任务明确说明 Blocked by: none 的理由。

随后设置 Parent 为 #27、按正文设置原生 Blocked by、选择工作性质/组件标签和 Milestone，并更新 #27 的依赖表。已开启子任务自动加入 Project；核对任务确实出现在“全部任务”中。更新依赖前检查是否形成环；不能仅删除原生阻塞或手动关闭前置来提前开工。

更换成员账号时，由小组确认新账号，并同步成员表、Issue 指派和项目访问权限。
