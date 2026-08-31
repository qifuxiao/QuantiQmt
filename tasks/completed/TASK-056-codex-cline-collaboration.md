---
id: TASK-056
title: Establish Codex-Cline GitHub collaboration protocol
status: completed
depends_on: [TASK-054, TASK-055]
spec_refs: []
allowed_paths:
  - AGENTS.md
  - .clinerules/00-quantiqmt-project.md
  - .clinerules/10-codex-handoff.md
  - ai/adapters/cline.md
  - ai/handoffs/TASK-056-REPAIR-v1.yaml
  - ai/handoffs/TASK-056-REPAIR-v2.yaml
  - ai/workflows/team-collaboration.md
  - scripts/validate_ai_handoff.py
  - tasks/AGENTS.md
  - tasks/templates/task-template.md
  - tasks/active/TASK-056-codex-cline-collaboration.md
  - tasks/backlog/TASK-056-codex-cline-collaboration.md
  - tasks/completed/TASK-056-codex-cline-collaboration.md
  - tasks/active/README.md
  - tasks/completed/README.md
  - tasks/index.yaml
  - tests/spec/test_codex_cline_collaboration_governance.py
  - tests/spec/test_miniqmt_m1_delivery_governance.py
  - tests/spec/test_validate_ai_handoff.py
forbidden_paths:
  - spec/**
  - src/**
  - migrations/**
  - pyproject.toml
  - poetry.lock
  - .github/**
  - tests/unit/**
  - tests/property/**
  - tests/contract/**
  - tests/integration/**
  - tasks/backlog/TASK-048-order-registration-broker-capability-binding.md
  - tasks/backlog/TASK-052-task-004-delivery-revalidation.md
  - tasks/backlog/TASK-053-dependency-sequencing-governance.md
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py tests/spec/test_validate_ai_handoff.py
    - poetry run ruff check scripts/validate_ai_handoff.py tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py tests/spec/test_validate_ai_handoff.py
    - poetry run ruff format --check scripts/validate_ai_handoff.py tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py tests/spec/test_validate_ai_handoff.py
    - poetry run python -c "from scripts.validate_specs import extract_front_matter, task_files; active=sorted(str(extract_front_matter(path).get('id')) for path in task_files() if extract_front_matter(path).get('status') == 'active'); assert active == ['TASK-056'], active"
    - poetry run python scripts/validate_ai_handoff.py --task tasks/active/TASK-056-codex-cline-collaboration.md --handoff ai/handoffs/TASK-056-REPAIR-v2.yaml --base-ref origin/main --head HEAD
    - git diff --check origin/main...HEAD
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_independent_review
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/95
    reviewed_head_sha: 70f0a731e72c26391f996326f5dc2009d8f0e580
    review_verdict: APPROVE
    reviewer: qfxyyy
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/95#pullrequestreview-5068093171
    merge_commit_sha: 0064bf238beffbbe053e927f1851b7dbc1e1016d
    review_submitted_at: '2026-08-31T15:15:46Z'
    merge_completed_at: '2026-08-31T15:16:42Z'
    ci_evidence: >-
      4/4 GitHub checks succeeded on the reviewed Head: two quality and two
      persistence-postgresql jobs from workflow runs 33402234453 and 33402227203.
    human_authorization_evidence: >-
      2026-08-31 user explicitly authorized an independent TASK-056 Closeout PR
      based on merge commit 0064bf238beffbbe053e927f1851b7dbc1e1016d, limited
      to the active-to-completed lifecycle projection and excluding spec,
      business code, CI, dependencies, self-approval, and merge.
---

# Objective

一次性建立 Codex 规划、Cline 实现、Codex 独立 Review、人类授权的跨服务器 GitHub
协作协议，并让后续每个 active task 携带版本化、区分 Planning Base 与 Implementation
Base 的 Codex Implementation Plan。

## Human authorization

- 2026-08-30 人类明确批准创建、激活并按三角色、两 PR 闭环实施 TASK-056。
- 人类批准以 GitHub commit、branch、PR 和精确 SHA 作为 Codex/Cline 不同服务器之间的
  唯一事实交接，不以聊天摘要代替 task、spec、CI、Review 或 merge 证据。
- 授权仅覆盖本任务 allowed paths 中的协作规则、任务模板和机器治理测试；不授权业务
  实现、`spec/` 变更、交易权限、部署、release、TASK-053 实施或下游任务激活。
- 本 Activation PR 只激活任务并冻结 Codex Plan；真正实现必须由 Cline 在后续独立
  Implementation PR 完成，不得在本 PR 顺带实现。
- 2026-08-30 独立 Codex Review 对 PR #95 的精确 Head
  `53112fd3e518e51ebebbefe6b1dbe869cbcfd7cc` 输出 `REQUEST_CHANGES`：发现工具规则复制
  业务契约、Base 未绑定、Review 模板漂移、closeout 授权歧义和测试假阳性。
- 2026-08-30 人类明确批准创建 `TASK-056-PLAN-v3` Amendment，并新增且仅新增
  `.clinerules/00-quantiqmt-project.md`、`ai/handoffs/TASK-056-REPAIR-v1.yaml`、
  `scripts/validate_ai_handoff.py`、`tests/spec/test_validate_ai_handoff.py` 四个授权路径。
- Plan Amendment 合并前，PR #95 必须保持 open 且不得 merge；Amendment 合并后由 Codex
  基于新的 main 精确 SHA 创建 GitHub 版本化 Repair Handoff Record，再由 Cline 修复。
- 2026-08-31 独立 Codex Review 对 PR #95 的精确 Head
  `bc6d762b1d770d962593c7d88e945852d50b9481` 输出 `REQUEST_CHANGES`：发现 merge-only
  删除/重引入可绕过 Record 不可变校验、Handoff 身份字段未绑定 active task/Packet/Plan，
  以及 `tasks/AGENTS.md` 仍错误授权 Reviewer 写入 completed。
- 2026-08-31 人类明确批准创建 `TASK-056-PLAN-v4` Repair Amendment；在 Plan v3 范围之上
  仅新增 `tasks/AGENTS.md` 与新的 Codex-only
  `ai/handoffs/TASK-056-REPAIR-v2.yaml`，并继续使用既有 TASK-056 validator/governance
  测试路径关闭上述三个 findings。该 Amendment 必须先独立合并到 main；其后 Codex 才可
  基于新的精确 Base 创建 v2 Handoff。授权不覆盖旧 Handoff 修改、业务代码、`spec/`、CI、
  依赖、merge、closeout 或任务完成状态迁移。

## Codex Implementation Plan

- Plan version: `TASK-056-PLAN-v4`
- Planning base SHA: `d0700f2ed67f2e53f55445c87444346c23bb6318`
- Observable outcome: Cline 从 GitHub 上的唯一 active task 获取 Codex Plan，基于其精确
  Implementation Base SHA 实现并提交 PR；新的 Codex Review 会话只读审查精确 Head；
  人类完成 merge 和 closeout 授权。

### Base identity decisions

- `Planning base SHA` 仅标识 Codex 形成和评审本 Plan 时所依据的 `main`；它必须是
  Implementation Base 的祖先，但不得与 Implementation Base 做相等比较。
- `Implementation Base SHA` 或后续 `Repair Base SHA` 不由 Cline 推断、选择或写回 task。
  Codex 必须在任何实现/修复修改前创建独立 commit，引入版本化、GitHub 可读取的 Handoff
  Record；Cline 只能从该 commit 开始工作且不得修改 Record。
- `ai/handoffs/TASK-056-REPAIR-v2.yaml` 必须至少冻结 `schema_version`、`task_id`、
  `packet_version`、`plan_version`、`planning_base_sha`、`expected_base_sha`、
  `expected_pr_base_sha`、`task_blob_sha`、阶段性 `allowed_paths` 和 `codex_only_paths`。
- Handoff identity 必须语义绑定当前验证对象：`schema_version` 必须是 validator 明确支持的
  版本 `1`，`task_id` 必须等于 active task front matter 的 `TASK-056`，`packet_version` 必须
  等于 Handoff 文件身份 `TASK-056-REPAIR-v2`，`plan_version` 必须等于本 task 中冻结的
  `TASK-056-PLAN-v4`；仅检查字段存在或 SHA 格式不得通过。
- `expected_base_sha` 必须是 Plan Amendment 合并后的精确 main SHA；
  `expected_pr_base_sha` 必须与它相等。两者未知时不得创建占位 Record 或开始修复。
- v2 Handoff introduction commit 必须恰有一个 parent，且该 parent 必须等于 Amendment
  合并后的精确 main SHA（即 v2 Record 的 `expected_base_sha`）；该 commit 对 v2 Handoff
  路径为 add-only，且不得包含任何其他路径。
- `task_blob_sha` 必须等于
  `git rev-parse <expected_base_sha>:tasks/active/TASK-056-codex-cline-collaboration.md`；Record
  必须把自身列入 `codex_only_paths`。validator 必须确认 Record 当前 blob 与首次引入它的
  Codex Handoff commit 完全一致，且 task 当前 blob 与 expected Base 中冻结值一致。
- Repair Handoff 的阶段性 `allowed_paths` 保留 Plan v3 已冻结的十个完整 PR 审计路径，并且
  只新增 `tasks/AGENTS.md` 与 `ai/handoffs/TASK-056-REPAIR-v2.yaml`。v1/v2 两份 Handoff
  都必须列入 `codex_only_paths` 且不得修改；不得新增 task lifecycle、spec、业务或 CI 路径。
- `scripts/validate_ai_handoff.py` 必须 fail-closed 地断言 Handoff expected Base、
  `git merge-base <base-ref> <head>` 和 Review 输入的 GitHub PR Base SHA 三者相等，Planning
  Base 是其祖先，task blob/Record 未漂移，且 exact Base...Head diff 全部通过路径授权。
- 对 v2 Handoff introduction 的后代锥与 supplied exact Head 祖先集合的交集，validator 必须
  使用不简化 merge 历史的真实 DAG 遍历，要求每个提交结果中的 v2 Record 都存在且 blob
  等于 introduction 的冻结 blob。外部同步 parent 可不含 v2 Record，但任何 introduction
  后的 descendant merge 结果均不得删除、修改或重新引入 Record；所有查询必须绑定 supplied
  `--head`，不得使用环境中的移动 `HEAD`。
- PR 创建前可省略 `--pr-base`，但独立 Review 必须从 GitHub 读取精确 PR Base 后使用
  `--pr-base <SHA>` 重跑；缺失、PR 非 OPEN、Base/Head 不相等或 Review 结束 Head 改变均
  只能 `BLOCKED`，不得降级为当前 merge-base 自动可信。
- Cline 必须在 Implementation Report 中分别报告 Planning Base、Handoff expected Base、
  GitHub PR Base 和 Head；Plan v4 Amendment 之前的 Base/Head 证据不得复用于修复后 Review。

### Authority and role decisions

- `AGENTS.md`、`spec/manifest.yaml`、唯一 active task 和全部 `spec_refs` 仍是共同权威链。
- `.clinerules/` 只提供 Cline 工具入口和跨服务器交接约束，不复制业务契约正文。
- Codex 负责选任务、规范/架构分析、设计、测试拆解、冲突判断和 Review，默认不写实现。
- Cline 负责测试先行、最小实现、验证、commit、push 和 Implementation PR；不得自行改变
  设计、task、spec、激活状态、Review 结论、merge 或 closeout。
- 独立 Review 只记录精确 Head verdict，不得创建、执行或授权状态迁移。
- 只有人类拥有任务激活、GitHub merge、branch protection 和 closeout/任务完成状态迁移
  授权；自动化只能执行已记录且可核验的人类授权。

### File-level change plan

- `AGENTS.md`: 增加持久角色边界和 GitHub 精确 SHA 交接规则，只引用既有权威来源。
- `.clinerules/00-quantiqmt-project.md`: 删除模拟账户、Kill Switch、真实资金、`xtquant`、
  订单链和 UNKNOWN 等业务/交易正文，只保留对 AGENTS、task、spec 的工具入口引用。
- `.clinerules/10-codex-handoff.md`: 定义 Base 校验、dirty worktree、`PLAN_BLOCKED`、PR
  evidence、Handoff Record 不可变约束、禁止直接 push main/self-approve/merge/closeout，
  并明确 Reviewer verdict 与人类 closeout 授权的边界。
- `ai/adapters/cline.md`: 要求 Cline 读取 task 内 Codex Plan，并输出标准 Implementation Report。
- `ai/handoffs/TASK-056-REPAIR-v1.yaml`: 保留历史冻结证据，任何 Agent 均不得修改。
- `ai/handoffs/TASK-056-REPAIR-v2.yaml`: 由 Codex 在 Amendment 合并后、实现修复前以
  独立 commit 创建，冻结精确 Repair Base、PR Base、task blob、Packet/Plan 和阶段性路径。
- `ai/workflows/team-collaboration.md`: 定义 Implementation Packet、Implementation Report、
  Repair Packet、精确 Base...Head Review、三种 verdict、Review 前后 Head 核验，以及
  Implementation/Closeout 两个 PR 生命周期和人类专属 closeout 授权。
- `scripts/validate_ai_handoff.py`: 在既有校验上增加 Handoff identity 语义绑定，并验证 v2
  introduction 后、supplied Head 可达的每个 descendant 提交结果始终保有冻结 Record blob。
- `tasks/AGENTS.md`: 删除 Reviewer 可写 completed 的冲突授权；独立 Review 仅提供证据，只有
  人类可授权 active → completed，自动化只能机械执行单独记录且可核验的人类授权。
- `tasks/templates/task-template.md`: 增加非规范性的版本化 Codex Implementation Plan 模板。
- `tests/spec/test_codex_cline_collaboration_governance.py`: 将 `tasks/AGENTS.md` 纳入全部持久
  协作文件扫描并拒绝 Reviewer/automation 作为 completed 状态迁移授权者的矛盾句。
- `tests/spec/test_validate_ai_handoff.py`: 增加真实 merge-only 删除/重引入 DAG 回归，以及
  `schema_version`、`task_id`、`packet_version`、`plan_version` 错误的函数级和 CLI 反例。
- `tests/spec/test_miniqmt_m1_delivery_governance.py`: 只同步 TASK-056 active 占用断言，保留
  TASK-054/055、MiniQMT 和 TASK-053 全部安全断言。

### Acceptance-to-test mapping

- Authority chain、无 active、dirty/plan gap fail-closed → 对明确章节和 MUST/MUST NOT 规范句式
  的结构测试；反例文本“允许 self-approve/merge/closeout”必须失败。
- `.clinerules/` reference-only → 扫描全部规则文件，拒绝当前已发现的交易正文类别和业务契约
  标识；每个文件必须仅把 AGENTS/task/spec 作为业务权威，不得因未知 token 未列入五词黑名单
  而默认通过。
- Handoff expected Base、merge-base、PR Base、Planning ancestor、task blob、Record immutable →
  `test_validate_ai_handoff.py` 的纯函数正反用例和 CLI 集成测试。
- Handoff identity → 由 active task ID、task 中 Plan version、Handoff 文件/Packet identity 和
  validator 支持版本共同校验；任一字段仅存在但语义不等时，函数与 CLI 都必须失败。
- merge-only 删除/重引入 → 临时真实 Git DAG 覆盖同步 merge、删除 Record 的 merge、恢复
  原始 blob 的 merge；即使最终 Head blob 等于 introduction，validator 仍必须拒绝。
- 三类交接物、两 PR 生命周期、精确 Base...Head、PR OPEN、Review 前后 Head、三 verdict、
  人类专属 closeout → team workflow 章节测试，并显式拒绝旧
  `origin/main..origin/<branch>`、仅两 verdict 及 Reviewer 可授权 closeout 的文本。
- 后续 task 必须携带 Plan version、Planning Base、Handoff Record、design/test/failure/stop
  fields，且禁止 Cline 修改 task/Record → task template 和 handoff 测试。
- TASK-056 唯一 active、054/055 completed、053 blocked → task/index/active README 投影测试。
- 禁止业务路径和规范变更 → 机器 validator 必须读取 task 与 Handoff Record，对
  `git diff --name-status --no-renames <expected Base>...<Head>` 的新增、修改、删除及 rename
  源/目标路径全部执行 allowed/forbidden 检查；解析失败、空 SHA 或命令失败均 fail-closed。

### Failure, concurrency, and recovery design

- Handoff Record 尚未由 Codex 创建、expected Base/PR Base/merge-base/task blob 任一不等、
  Planning Base 不是 expected Base 祖先、Record 被 Cline 修改、工作区有非预期修改、active
  task 数量不为一、task/spec 冲突、allowed paths 不足或设计缺口时，Cline 必须停止并返回
  `PLAN_BLOCKED` 及证据。
- v2 Handoff 合入 PR #95 及其后续修复全过程禁止 rebase 和 force-push；Implementation
  Agent 也不得直接 push main、降低测试或自行修改 task/spec 解决阻塞。
- Codex Review 必须先验证 PR OPEN、精确 Base/Head 和三点 diff，并在结束时重新读取 Head；
  Head 改变后旧 verdict 失效并从头 Review。
- Implementation PR 合并不等于 task completed；必须另建 Closeout PR 核验 Review、CI、
  merge 和人类授权。任何外部事实不可核验时保持 pending/prohibited。

### Implementation order

1. 先独立 Review 并由人类合并本 Plan v4 Amendment；不得把授权扩展与实现修复放在
   同一未合并 commit 中自我生效。
2. Amendment 合并后，Codex 读取新 main 精确 SHA，创建只含
   `ai/handoffs/TASK-056-REPAIR-v2.yaml` 的独立 Handoff commit；该 Record 的 expected Base 和
   expected PR Base 均为新 main SHA，并记录 task blob SHA、`TASK-056-PLAN-v4` 与
   `TASK-056-REPAIR-v2` identity。该 commit 必须恰有一个 parent 且等于该精确 Base，对 v2
   路径必须是 add-only，并且不得包含其他路径；旧 v1 Record 必须保持 byte-for-byte 不变。
3. 经人类授权的 Implementation Agent fetch Handoff commit，将精确新 main/Handoff 合入
   PR #95 分支；合入与后续修复全过程禁止 rebase 和 force-push。在任何 repair 修改前运行
   validator，Base/Record 不一致则 `PLAN_BLOCKED`。
4. 经人类授权的 Implementation Agent 先新增失败的治理与 validator 正反测试，再只修改
   `tasks/AGENTS.md` 与 `scripts/validate_ai_handoff.py` 完成最小修复；不得借机修改其他已
   授权但与本轮三个 findings 无关的治理文件。
5. PR 创建后从 GitHub 读取精确 PR Base/Head，使用 validator 的 `--pr-base` 再审计；更新
   Implementation Report 和 Repair evidence 后正常 push，不合并、不 self-approve、不 closeout。
6. 新 Codex Review 会话对新的精确 Base...Head 从头 Review；旧 Head
   `53112fd3e518e51ebebbefe6b1dbe869cbcfd7cc` 的证据和 verdict 不得复用。

### PLAN_BLOCKED conditions

- 规范或 Accepted ADR 与本 Plan 冲突。
- 必须修改 forbidden path、业务契约、CI、依赖或 GitHub 权限才能完成。
- Handoff Record 缺失/不是 Codex 独立 commit、expected Base 未冻结、PR Base/merge-base 不等、
  task blob/Record 漂移、Planning Base 不再是 expected Base 祖先，或 active task/依赖变化。
- 无法执行 verification commands，或 Cline 无法证明 diff 只覆盖 allowed paths。

## Non-goals

- 不修改任何业务代码、规范、migration、依赖、CI、交易配置或 GitHub 权限。
- 不激活、实施或改变 TASK-053、TASK-052、TASK-048 及其依赖或 acceptance。
- 不创建同名 `.clinerules` 单文件，不把 `.clinerules/` 变成平行 `spec/`。
- 不声称文本规则能够替代 CI、branch protection、独立 Review 或人类 merge。
- 不修改 `.github/` 建立自动 PR 查询；PR OPEN/Base/Head 由独立 Review 从 GitHub 读取后
  作为 validator 的精确输入，未知时必须 `BLOCKED`。

## Deliverables

- 项目级 Codex/Cline 职责和 GitHub 事实交接规则。
- Cline 固定 handoff 约束和标准 Implementation Report。
- 三类交接物、两 PR 生命周期及 Repair 循环的工具中立工作流。
- Codex-authored、GitHub 版本化且 Implementation Agent 不可修改的 Handoff Record。
- 可对构造输入执行的 Base/PR Base/task blob/Record/path fail-closed validator。
- 可复用的 task-level Codex Implementation Plan 模板。
- 覆盖角色隔离、精确 SHA、冲突/否定语义、validator 正反例和队列投影的机器治理测试。

## Acceptance criteria

- [x] 持久规则明确 Codex 决策、Cline 产能、Codex 独立验收、人类最终授权的角色边界。
- [x] Cline 必须读取 Codex Plan，并在无 active、Base 不匹配、dirty 或设计缺口时 fail-closed。
- [x] 全部 `.clinerules/` 只引用 AGENTS/task/spec，不复制模拟账户、交易开关、Broker/API、
  订单链、UNKNOWN/reconciliation、Event、DTO、状态机、错误码或其他业务契约正文。
- [x] Codex-authored v2 Handoff Record 在修复前冻结 expected Base/PR Base/task blob/Plan/Packet/
  阶段路径，Implementation Agent 修改或缺失 Record 时 fail-closed。
- [x] Validator 将 `schema_version`、`task_id`、`packet_version`、`plan_version` 分别绑定到
  支持版本、active task、v2 Packet 和 Plan v4；任一语义不匹配均 fail-closed。
- [x] v2 introduction 后、supplied Head 可达的每个 descendant 提交结果都保有同一冻结
  Record blob；merge-only 删除、恢复原 blob 或重新引入均被真实 Git 拓扑测试拒绝。
- [x] 机器 validator 对构造输入证明 expected Base、merge-base、PR Base 三者必须相等，
  并覆盖 missing/mismatch、Record/task 漂移、rename、outside allowed 和 forbidden 反例。
- [x] Cline Report 包含 Base/Head SHA、branch/PR、changed files、逐项 acceptance、命令退出码、
  未验证范围、风险、spec deviations 和 allowed-path diff 结论。
- [x] 所有 Review 入口要求 PR OPEN、精确 Base/Head、祖先检查、精确 `Base...Head` diff、
  结束 Head 再核验和三种 verdict；禁止移动 ref 双点范围及仅两 verdict 模板。
- [x] Implementation PR 与 Closeout PR 分离；Cline 不得 self-approve/merge/closeout。
- [x] Reviewer 只记录 verdict，只有人类可授权 closeout/状态迁移，所有规则无“人类或
  Reviewer 均可授权”的歧义。
- [x] `tasks/AGENTS.md` 不再授权 Reviewer 写入 completed，并被全部持久协作文件否定扫描覆盖。
- [x] Task template 明确区分 Planning Base 与 Codex-authored Handoff Record 中的 expected
  Base，并包含设计、文件计划、测试映射、失败设计和 PLAN_BLOCKED 条件。
- [x] 没有修改 spec、业务代码、migration、依赖、CI、交易权限或其他任务 scope；相对
  Plan v3 仅新增 `tasks/AGENTS.md` 和 v2 Handoff 路径，finding 实现只修改 v2 Handoff、
  validator、`tasks/AGENTS.md` 与两份既有 TASK-056 validator/governance 测试。
- [x] changed-path membership audit 和所有 verification commands 通过，独立 Review
  后才可进入 closeout。

## Required evidence

- 使用 `ai/workflows/implement-task.md` 格式报告 changed files、逐项 acceptance、命令与
  exit code、未验证范围、风险和 spec deviations。
- Implementation Report 分别记录 Planning Base、Handoff Record commit、expected Base、
  GitHub PR Base/Head、branch/PR，以及以 expected Base 为左端的完整 path audit。
- Review evidence 包含 PR OPEN、开始/结束 Base/Head、validator `--pr-base` 输出和全部命令
  exit code；Head 改变时旧 Review 失效。
- Closeout 记录独立 Review、CI、merge commit 和可核验的人类授权；Reviewer verdict 不是
  closeout 授权，未知事实不得猜测。

## Final Review and closeout evidence

- 独立只读 Review 对最终 implementation Head
  `70f0a731e72c26391f996326f5dc2009d8f0e580` 给出 `APPROVE`；修正两项 Review 指令错误后，
  未发现 blocking finding，TASK-056 四文件测试为 `131 passed, 0 failed, 0 skipped`，15 项
  真实 Git topology 测试全部非 skip 通过。
- 不同作者的 collaborator `qfxyyy` 于 `2026-08-31T15:15:46Z` 对同一精确 Head 提交正式
  GitHub `APPROVED` Review：
  https://github.com/qifuxiao/QuantiQmt/pull/95#pullrequestreview-5068093171
- 该 Head 的 4/4 GitHub checks 全部成功：
  [quality pull_request](https://github.com/qifuxiao/QuantiQmt/actions/runs/33402234453/job/99521096256)、
  [quality push](https://github.com/qifuxiao/QuantiQmt/actions/runs/33402227203/job/99521074950)、
  [persistence pull_request](https://github.com/qifuxiao/QuantiQmt/actions/runs/33402234453/job/99521096464) 和
  [persistence push](https://github.com/qifuxiao/QuantiQmt/actions/runs/33402227203/job/99521074764)。
- PR #95 于 `2026-08-31T15:16:42Z` 由 `qfxyyy` 合并到 `main`，merge commit 为
  `0064bf238beffbbe053e927f1851b7dbc1e1016d`；该 commit 的第二 parent 精确等于 reviewed Head。
- 2026-08-31 人类随后单独明确授权基于上述 merge commit 创建 TASK-056 Closeout PR，并仅
  机械执行 active → completed 生命周期投影；授权明确排除 `spec/`、业务代码、CI、依赖、
  self-approval 和 Closeout PR merge。
- Closeout 不授权 release、下游任务激活、部署或任何交易能力；`release_status` 继续为
  `prohibited`，TASK-053 继续保持 backlog/blocked。

## Closeout verification

- Closeout 分支基于 `origin/main@0064bf238beffbbe053e927f1851b7dbc1e1016d` 创建，未重写
  implementation 历史，也未修改 v1/v2 Handoff Record。
- 生命周期变更前，冻结 Base/Head/PR Base validator、spec validator、Ruff、mypy、唯一
  `TASK-056` active assertion 和精确 implementation diff check 均 exit 0。主分支合并前移后，
  可选 checkout smoke 如预期不再适用；核心真实 Git topology 测试仍为 `15 passed, 0 skipped`。
- 生命周期投影完成后，`scripts/validate_specs.py`、mypy 和空 active task assertion 均 exit 0；
  修复 Closeout Review finding 后四文件治理测试为 `134 passed, 0 failed, 1 skipped`；新增四项
  回归测试锁定 completed/frozen-active 路径分离和仅允许的两种 skip 原因。唯一实际 skip 是
  已单独报告的可选 checkout smoke，因为移动的 `origin/main` 已不再等于冻结 Repair Base。
- Closeout 仅移动并更新 TASK-056、active/index 投影和三个直接引用其生命周期路径的治理测试；
  未修改 `spec/`、`src/`、`.github/`、migration、依赖、Handoff Record、业务代码或其他任务。
  规范偏差为 none。

## Risks and rollback

- 本地模型可能不遵守文本规则；实际门禁仍依赖 task validator、CI、精确 diff、独立
  Review、branch protection 与人类 merge。
- 过度复制规范会造成漂移；工具规则只允许指向权威来源。
- 回滚只恢复本任务产生的协作规则、模板、测试和任务投影，不影响业务代码或运行状态。
