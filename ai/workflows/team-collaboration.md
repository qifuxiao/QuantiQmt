# Workflow: Multi-Agent Team Collaboration

本项目允许多名人类成员分别使用 Codex、Claude Code、Gemini、Cursor 等 AI Agent 协作。所有工具共享同一套仓库规则：根 `AGENTS.md`、`spec/README.md`、`tasks/README.md` 和当前 active task 是工作入口。

## 工具中立会话角色

| 角色 | 职责 | 是否写 Implementation PR |
|---|---|---|
| Coordinator | 项目进展、任务拆分、设计、Implementation Packet / Repair Packet 和冲突判断 | 默认不写 |
| Implementation Agent | 执行一个 active task，测试先行并按冻结路径实现、验证、提交和推送 | 是，且同一 PR 仅一个 writer |
| Environment Verification Agent | 在实际具备的 OS/外部环境产生 capability-bound environment evidence | 否；只补证据 |
| Independent Review Agent | 只读审查他人精确 Head，输出 P0/P1/P2/P3 和三种 verdict | 否 |
| Human | 授权 activation、外部副作用、GitHub Approval/merge 和 closeout | 不由 Agent 代替 |

Codex、Cline、Claude Code、Gemini、Cursor 是 tool/adapter，不是权限角色。会话开头必须声明
role、task ID、tool、OS、允许/禁止路径、是否可以写文件和实际环境能力。

### Implementation assignment 和切换

开始写入前，人类必须在 GitHub 留下可核验的 assignment。Implementation Agent 必须冻结：

- role、tool、OS；
- 精确 Starting Head；
- human evidence URL（必须是持久 GitHub comment/review URL，聊天摘要不够）；
- `single writer: true` 以及 Coordinator/旧 writer 的停止点。

`tool` 必须是最长 64 字符、无空白/控制字符的工具中立安全标识符；`OS` 必须明确为
Windows、Linux 或 macOS。空值、仅空白、非字符串或不受支持的 OS 均 fail-closed。

中途切换必须由人类另行记录 previous agent、next agent、授权范围和 previous agent 的
stop Head；新 Agent 的 Starting Head 必须等于该 stop Head。旧 Agent 从该点停止写入，缺少
任一字段或存在并发 writer 时返回 `PLAN_BLOCKED`。

`ordered PR/branch single-writer` 使用
`ai/schemas/agent-assignment.schema.yaml` 的有序事件，不从若干可选 snapshot 字段猜测状态。
正式事件只有 `ASSIGN`、`STOP`、`SWITCH`，`sequence` 必须严格递增；任一时刻最多一个 active
writer。agent identity 是不复用的会话/writer 标识，不等同于 tool/OS；因此同一 tool/OS 的两个
独立会话仍可在 Human 授权下切换。`SWITCH` 必须紧跟可核验的前任 `STOP`，并由 Human GitHub
evidence 证明 previous/next agent。前任 `stop_head_sha`、`previous_agent_stop_head_sha`、
新任 `starting_head_sha` 和当时 `pr_head_sha`
必须完全相等；乱序、双 writer、身份复用或任一 Head 漂移均 fail-closed。

### Live GitHub authority

Assignment 不是 caller 参数或本地文件。Human 必须在目标 PR 发布未编辑的 canonical
`QUANTIQMT_GITHUB_AUTHORITY_V1` issue comment，Repair Handoff 冻结 repository、PR、Base/Head
branch、comment ID/URL/author/timestamps/raw-body digest 以及 producer allowlist。正式 gate 使用
固定 `https://api.github.com` 的有界、禁止重定向 HTTPS GET，实时确认 PR OPEN、非 draft、
Base/Head/branch 和 assignment comment；API 错误、超时、限流、编辑、跨 PR 或 digest 漂移均
`BLOCKED`。caller 不得用 `--pr-head`、`--pr`、`--branch` 或本地 assignment authority。
The GitHub API validates the canonical environment evidence comment with no redirects.

## 分工原则

- 一个 Implementation Agent 一次只处理一个 active task。
- 不让两个 Implementation Agent 同时修改同一任务、分支或同一批文件。
- 实现者不得自己批准自己的 PR；Independent Review Agent 必须是未参与该 Head 实现的会话。
- Independent Review Agent 不得修改文件；发现问题后输出可复现证据和最小修复方向。
- **任务激活、PR 合并（merge）、closeout 授权、和任务状态转移（active → completed）
  均为人类独占操作。Independent Review Agent 仅记录结论，不能授权 closeout。**
- 连接外部 Broker/Mini QMT 或产生委托等副作用同样是 human-only。模拟委托必须由 separate
  active task 和单独 human evidence URL 明确授权；real-money trading 始终 forbidden。

## 标准流程

```text
Coordinator 判断下一任务并生成 Packet
→ Human 在 GitHub 分配唯一 Implementation Agent
→ Implementation Agent 实现并推送 PR
→ Environment Verification Agent 对 required lane 补充精确 Head 证据
→ Independent Review Agent 只读审查（APPROVE / REQUEST_CHANGES / BLOCKED）
→ REQUEST_CHANGES 则 Implementation Agent 修复后重新 Review
→ APPROVE 后人类合并 PR
→ 人类单独记录并授权 closeout：协调会话仅机械检查 main、创建/执行 completion PR
→ 再选择下一任务
```

实现 PR 合并不等于任务完成。独立 Review 只提供完成证据；只有人类可以授权 task 从
`tasks/active/` 移入 `tasks/completed/`。自动化只能机械执行已经单独记录且可核验的人类授权，
不能作为替代授权者。

## 交接物与 PR 生命周期

### 三类交接物

| 交接物 | 生产者 | 消费者 | 内容 |
|---|---|---|---|
| **Implementation Packet** | Coordinator（当前为 Codex-authored） | Implementation Agent | 精确 Implementation Base SHA、设计、文件计划、测试映射、失败设计、PLAN_BLOCKED 条件 |
| **Implementation Report** | Implementation Agent | Independent Review Agent / Human | assignment、Base/Head、branch/PR、changed files、acceptance、命令退出码、environment evidence、未验证范围、风险、spec deviations、path audit |
| **Repair Packet** | Coordinator（当前为 Codex-authored） | Implementation Agent | 基于精确 Head Review 的修复指令，限定 allowed_paths |

### 两 PR 生命周期

**Implementation PR** 与 **Closeout PR** 必须分离：

1. **Implementation PR**：唯一 Implementation Agent 推送实现变更。Independent Review Agent 只读审查
   **精确 Head SHA**，结论仅限 `APPROVE`、`REQUEST_CHANGES` 或 `BLOCKED`。
   Head SHA 改变后旧 Review 自动失效（invalidated），必须重新 Review。
2. **Closeout PR**：在 Implementation PR 合并后且人类授权已经单独记录并可核验时创建，
   核验独立 Review 结论、CI 结果、merge commit 和人类授权，将 task 从
   `tasks/active/` 移入 `tasks/completed/` 并更新 `tasks/index.yaml`。自动化只能机械执行该
   人类授权，不能自行授权创建 Closeout PR 或状态迁移。

### Path audit

Implementation Report 必须包含以 Implementation Base 为左端的完整
`git diff --name-only --no-renames <Base>...HEAD` **path audit**（路径审计），
确认所有变更路径属于 task `allowed_paths` 且未命中 `forbidden_paths`。

## 开发指令最小模板

```text
你是被 GitHub assignment 明确分配的 Implementation Agent。只执行 TASK-XXX。

请读取 AGENTS.md、spec/README.md、spec/manifest.yaml、tasks/active/TASK-XXX.md，以及 TASK-XXX 的全部 spec_refs。

只允许修改 TASK-XXX allowed_paths，禁止修改 forbidden_paths。

先记录 implementation assignment、verification lanes、environment evidence 和 exact Head。
目标：完成 TASK-XXX acceptance criteria，运行 verification.commands，提交并推送。

不要合并 PR，不要把任务移动到 completed。
最终回复必须包含：提交 SHA、修改文件、逐项验收证据、验证命令和结果、unverified scope、
环境 lane、未解决风险。
```

## Review 指令最小模板

```text
你是独立 Review Agent。请只读审查 PR #NN / TASK-XXX，不要修改任何文件。

前置条件（不满足则返回 BLOCKED）：
- PR 状态必须为 OPEN（Review 开始和结束时各检查一次）
- 记录 Beginning Head SHA（`gh pr view NN --json headRefOid --jq .headRefOid`）
- 记录 GitHub PR Base SHA（`gh pr view NN --json baseRefOid --jq .baseRefOid`）
- Base 必须等于 Handoff Record 中的 expected_base_sha
- 将 GitHub PR Base 以 `--pr-base` 传入 validator
- 证明 expected_base_sha == PR Base SHA == merge-base(expected_base, head)
- 证明 Planning Base 是 Implementation Base 的祖先
- 审查范围必须是精确 Base...Head 三段 diff（`git diff --name-only --no-renames <Base>...<Head>`）

请读取 AGENTS.md、ai/review/**、spec/README.md、spec/manifest.yaml、tasks/active/TASK-XXX.md，以及 TASK-XXX 的全部 spec_refs。

请运行 TASK-XXX verification.commands（含 --pr-base），并额外检查 allowed_paths、forbidden_paths、交易安全、幂等、恢复、金额精度和越权依赖。

完成后重新读取 Ending Head SHA（`gh pr view NN --json headRefOid --jq .headRefOid`），
必须等于 Beginning Head SHA；否则结论为 BLOCKED。

输出格式：
- Findings，按 P0/P1/P2/P3 排序
- 已确认通过的部分
- 验证结果
- 最终结论只能是 APPROVE、REQUEST_CHANGES 或 BLOCKED
```

Review 结论由 Review Agent 记录，但**不能授权 closeout**。任务激活、PR 合并、
和任务状态转移（active → completed）仅由人类授权。

## Verification lanes 与 environment evidence

| lane | 可执行环境 | 证据边界 |
|---|---|---|
| `portable` | Linux 或 Windows | 静态检查、spec、unit/contract、Broker Simulator 与不导入 vendor runtime 的测试；Implementation Agent 必须执行环境支持的全部命令，不能全部 skip |
| `windows` | 实际 Windows Agent | Windows-only compatibility/integration；Linux 结果不得标为通过 |
| `windows_miniqmt` | 实际 Windows、可用 Mini QMT 和 task-approved `xtquant` | 默认只读；缺客户端、session、模拟账号 allowlist 或授权均为 `BLOCKED` |

Environment evidence 的版本化契约是
`ai/schemas/agent-environment-evidence.schema.yaml`，assignment 契约是
`ai/schemas/agent-assignment.schema.yaml`。`scripts/validate_agent_environment.py` 是唯一正式
machine gate；文档、adapter 和测试不得维护第二套 parser 或 pseudo-validator。

Environment evidence 有两个互不替代的验证层：

1. **canonical comment/schema gate**：environment evidence 必须是目标 PR 上未编辑的
   `QUANTIQMT_ENVIRONMENT_EVIDENCE_V1` issue comment。envelope 记录 task、Plan、frozen Base、
   live exact Head、repository/PR、assignment comment 和 producer agent/login/role/tool/OS/lanes；
   每条 record 记录 lane、`requirement`（`required` / `optional` / `not_applicable`）、Python/Poetry
   及适用的脱敏 xtquant 版本、original command、exit code、
   executed/passed/failed/skipped、RFC3339 `timestamp`、`sanitized_evidence: true`、显式
   `unverified_scope`（允许空字符串但不得缺失）。task/Base/Head 必须与 frozen Handoff 和 live
   PR 精确相等，不能只检查 SHA 格式。GitHub API 回读 comment author、URL、issue URL、
   created/updated 和正文；只有 Implementation Agent
   和 Environment Verification Agent 可以生产环境证据；Independent Review Agent 不可以。
   xtquant 使用 `{source, value, verified}` provenance；source 只接受可信 package metadata 或
   vendor API，value 是最长 64 字符的 opaque sanitized token，不猜测 semver。路径、空白、
   `userdata_mini`、账号/secret/credential 标签和长纯数字 token 均拒绝；未知 source/value
   保持 unverified/`BLOCKED`，不得从 runtime path 猜测。
2. **required-lane satisfaction gate**：validator 从 exact Head 的唯一 active task 与冻结 Handoff
   自行读取 deep-equal 的 required lanes、prohibited lanes 和 opaque exact command strings。
   lane commands 必须对 `verification.commands` 形成无遗漏、无重复的精确分区；caller/evidence
   不得提供、覆盖或缩减 expected commands。完整 record set 必须无缺失、无意外或替代命令；
   每条 schema/identity 均有效、
   `exit_code == 0`、`failed == 0`、计数为非负整数且内部一致、`executed > 0`。skip 只能在
   task 对该 command 明确给出 allowance 时出现，且必须写入非空 `unverified_scope`。producer
   必须命中 Handoff allowlist；Implementation Agent 还必须等于 canonical assignment 的 active writer。

单条格式正确不等于 required lane 已满足。required lane 缺少能力或 satisfaction gate 未通过时
保持 pending/`BLOCKED`，不能用其他 lane、mock 或文字说明替代。Head 改变后，旧 environment
evidence 和 Review verdict 全部失效，必须以新的 expected Base/exact Head 重跑完整命令集合。

Environment Verification Agent 只报告实际能力和证据，不授权任务、外部副作用或状态迁移。
`windows_miniqmt` 还必须证明客户端可用、`xtquant` 已被 task 允许、`userdata_mini` 已核验、
session 唯一且账号精确命中模拟 allowlist；任一未知即 fail-closed。
每条 record 必须显式记录 `real_money: false`、`miniqmt_connection`、`account_query` 和
`simulation_order`。capability 与 side-effect authorization 是不同字段；record 不能自我授权
模拟委托；只有 satisfaction gate 的调用方提供 trusted caller authorization context，证明当前 separate
active task 和可核验 Human GitHub evidence 后才能接受。TASK-057 不提供该权限；real-money
trading 始终 forbidden。

## 环境门槛

- 需要 PostgreSQL 的 Review 必须设置 `QUANTIQMT_POSTGRES_DSN` 并连接真实 PostgreSQL。
- Poetry、sandbox、worktree 和 build 验证必须遵循 `ai/workflows/poetry-verification.md`；不得
  用 bundled Python 或直接 pytest/Ruff/mypy 冒充项目规定的原始 `poetry run` 命令。
- TASK-057 不构建通用 PowerShell/POSIX parser，也不使用有限 shell 关键词黑名单。task/Handoff
  冻结的 command 是 opaque exact string；可执行性和宿主权限仍由 task review、adapter 与最小
  sandbox authorization 控制，evidence 只能逐字覆盖该集合。
- 测试无法运行时不得 APPROVE；必须明确未验证范围。
- GitHub connector 不可用时，可使用本地 Git refs、PR head refs 和用户提供的 commit SHA 做只读复验，但必须说明发布/读取限制。

## 冲突处理

- 发现 task 缺少 DTO、Event、Workflow、Repository、错误码或状态机契约时，停止实现并请求 spec-change task。
- 发现另一个成员正在修改同一 allowed_paths 时，暂停并由协调会话重新分配。
- 发现 Review 结论冲突时，以更严格的阻断 finding 为准，直到可复现证据消除分歧。
- 不用临时重构、全仓库格式化或依赖升级来“顺手”解决任务外问题。
# Governance handoff

The coordinator records task queue state; the implementation agent records delivery evidence; an independent reviewer records the verdict against a concrete head; and a human member authorizes merge/release and any status transition. These roles are intentionally separate. Unverifiable history is never filled with guessed approvals.
