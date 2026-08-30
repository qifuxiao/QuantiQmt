# Workflow: Multi-Agent Team Collaboration

本项目允许多名人类成员分别使用 Codex、Claude Code、Gemini、Cursor 等 AI Agent 协作。所有工具共享同一套仓库规则：根 `AGENTS.md`、`spec/README.md`、`tasks/README.md` 和当前 active task 是工作入口。

## 会话角色

每名项目成员建议维护三个会话。

| 会话 | 职责 | 是否写代码 |
|---|---|---|
| 项目协调会话 | 项目进展分析、任务拆分、指令生成、冲突判断、合并后收尾规划 | 默认不写 |
| 开发会话 | 执行一个 active task，按 allowed_paths 实现、验证、提交、推送 PR | 是 |
| Review 会话 | 只读审查他人 PR，运行验证，输出 P0/P1/P2/P3 与 `APPROVE`、`REQUEST_CHANGES` 或 `BLOCKED` | 否 |

会话开头必须声明角色、任务 ID、允许路径、禁止路径和是否可以写文件。

## 分工原则

- 一个开发会话一次只处理一个 active task。
- 不让两个开发会话同时修改同一任务或同一批文件。
- 成员 A 的开发 PR 由成员 B 的 Review 会话审查；成员 B 的开发 PR 由成员 A 的 Review 会话审查。
- 开发者不得自己批准自己的 PR。
- Review Agent 不得修改文件；发现问题后输出可复现证据和修复方向。
- **任务激活、PR 合并（merge）、closeout 授权、和任务状态转移（active → completed）
  均为人类独占操作。Review Agent 仅记录结论，不具备授权权。**

## 标准流程

```text
协调会话判断下一任务
→ 生成开发指令
→ 开发会话实现并推送 PR
→ 对方 Review 会话只读审查（APPROVE / REQUEST_CHANGES / BLOCKED）
→ REQUEST_CHANGES 则开发会话修复后重新 Review
→ APPROVE 后人类合并 PR
→ 人类授权 closeout：协调会话检查 main、创建/执行 completion PR
→ 再选择下一任务
```

实现 PR 合并不等于任务完成。任务只有在独立 Review 通过，并由人类或授权流程把 task 从 `tasks/active/` 移入 `tasks/completed/` 后，才算 completed。

## 交接物与 PR 生命周期

### 三类交接物

| 交接物 | 生产者 | 消费者 | 内容 |
|---|---|---|---|
| **Implementation Packet** | Codex | Cline | 精确 Implementation Base SHA、设计、文件计划、测试映射、失败设计、PLAN_BLOCKED 条件 |
| **Implementation Report** | Cline | Codex Review / 人类 | Base/Head SHA、branch/PR、changed files、逐项 acceptance 证据、命令退出码、未验证范围、风险、spec deviations、path audit 结论 |
| **Repair Packet** | Codex | Cline | 基于精确 Head Review 的修复指令，限定 allowed_paths |

### 两 PR 生命周期

**Implementation PR** 与 **Closeout PR** 必须分离：

1. **Implementation PR**：Cline 推送实现变更。独立 Codex Review 会话只读审查
   **精确 Head SHA**，结论仅限 `APPROVE`、`REQUEST_CHANGES` 或 `BLOCKED`。
   Head SHA 改变后旧 Review 自动失效（invalidated），必须重新 Review。
2. **Closeout PR**：在 Implementation PR 合并后，由人类或授权流程创建，
   核验独立 Review 结论、CI 结果、merge commit 和人类授权，将 task 从
   `tasks/active/` 移入 `tasks/completed/` 并更新 `tasks/index.yaml`。

### Path audit

Implementation Report 必须包含以 Implementation Base 为左端的完整
`git diff --name-only --no-renames <Base>...HEAD` **path audit**（路径审计），
确认所有变更路径属于 task `allowed_paths` 且未命中 `forbidden_paths`。

## 开发指令最小模板

```text
你是开发 Agent。只执行 TASK-XXX，不要做其他任务。

请读取 AGENTS.md、spec/README.md、spec/manifest.yaml、tasks/active/TASK-XXX.md，以及 TASK-XXX 的全部 spec_refs。

只允许修改 TASK-XXX allowed_paths，禁止修改 forbidden_paths。

目标：完成 TASK-XXX acceptance criteria，运行 verification.commands，提交并推送。

不要合并 PR，不要把任务移动到 completed。
最终回复必须包含：提交 SHA、修改文件、逐项验收证据、验证命令和结果、未解决风险。
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

## 环境门槛

- 需要 PostgreSQL 的 Review 必须设置 `QUANTIQMT_POSTGRES_DSN` 并连接真实 PostgreSQL。
- 如果 `poetry` 不在 PATH，优先使用 Windows 绝对路径 fallback。
- 测试无法运行时不得 APPROVE；必须明确未验证范围。
- GitHub connector 不可用时，可使用本地 Git refs、PR head refs 和用户提供的 commit SHA 做只读复验，但必须说明发布/读取限制。

## 冲突处理

- 发现 task 缺少 DTO、Event、Workflow、Repository、错误码或状态机契约时，停止实现并请求 spec-change task。
- 发现另一个成员正在修改同一 allowed_paths 时，暂停并由协调会话重新分配。
- 发现 Review 结论冲突时，以更严格的阻断 finding 为准，直到可复现证据消除分歧。
- 不用临时重构、全仓库格式化或依赖升级来“顺手”解决任务外问题。
# Governance handoff

The coordinator records task queue state; the implementation agent records delivery evidence; an independent reviewer records the verdict against a concrete head; and a human member authorizes merge/release and any status transition. These roles are intentionally separate. Unverifiable history is never filled with guessed approvals.
