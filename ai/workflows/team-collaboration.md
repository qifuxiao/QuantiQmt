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

中途切换必须由人类另行记录 previous agent、next agent、授权范围和 previous agent 的
stop Head；新 Agent 的 Starting Head 必须等于该 stop Head。旧 Agent 从该点停止写入，缺少
任一字段或存在并发 writer 时返回 `PLAN_BLOCKED`。

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

每份 environment evidence 必须记录 task、Base、exact Head、role、tool、OS、Python/Poetry
版本（适用时含脱敏 xtquant 版本）、原始 command、exit code、passed/failed/skipped 数量、时间、
脱敏证据、unverified scope 和 evidence URL。required lane 缺少能力时保持 pending/`BLOCKED`，
不能用其他 lane、mock 或文字说明替代。Head 改变后，旧 environment evidence 和 Review verdict
全部失效，必须在新 Head 重跑。

Environment Verification Agent 只报告实际能力和证据，不授权任务、外部副作用或状态迁移。
`windows_miniqmt` 还必须证明客户端可用、`xtquant` 已被 task 允许、`userdata_mini` 已核验、
session 唯一且账号精确命中模拟 allowlist；任一未知即 fail-closed。
任何模拟委托仍要求 separate active task 和可核验 human evidence URL；real-money trading
始终 forbidden。

## 环境门槛

- 需要 PostgreSQL 的 Review 必须设置 `QUANTIQMT_POSTGRES_DSN` 并连接真实 PostgreSQL。
- Poetry、sandbox、worktree 和 build 验证必须遵循 `ai/workflows/poetry-verification.md`；不得
  用 bundled Python 或直接 pytest/Ruff/mypy 冒充项目规定的原始 `poetry run` 命令。
- 测试无法运行时不得 APPROVE；必须明确未验证范围。
- GitHub connector 不可用时，可使用本地 Git refs、PR head refs 和用户提供的 commit SHA 做只读复验，但必须说明发布/读取限制。

## 冲突处理

- 发现 task 缺少 DTO、Event、Workflow、Repository、错误码或状态机契约时，停止实现并请求 spec-change task。
- 发现另一个成员正在修改同一 allowed_paths 时，暂停并由协调会话重新分配。
- 发现 Review 结论冲突时，以更严格的阻断 finding 为准，直到可复现证据消除分歧。
- 不用临时重构、全仓库格式化或依赖升级来“顺手”解决任务外问题。
# Governance handoff

The coordinator records task queue state; the implementation agent records delivery evidence; an independent reviewer records the verdict against a concrete head; and a human member authorizes merge/release and any status transition. These roles are intentionally separate. Unverifiable history is never filled with guessed approvals.
