---
id: TASK-056
title: Establish Codex-Cline GitHub collaboration protocol
status: active
depends_on: [TASK-054, TASK-055]
spec_refs: []
allowed_paths:
  - AGENTS.md
  - .clinerules/10-codex-handoff.md
  - ai/adapters/cline.md
  - ai/workflows/team-collaboration.md
  - tasks/templates/task-template.md
  - tasks/active/TASK-056-codex-cline-collaboration.md
  - tasks/backlog/TASK-056-codex-cline-collaboration.md
  - tasks/completed/TASK-056-codex-cline-collaboration.md
  - tasks/active/README.md
  - tasks/completed/README.md
  - tasks/index.yaml
  - tests/spec/test_codex_cline_collaboration_governance.py
  - tests/spec/test_miniqmt_m1_delivery_governance.py
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
    - poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py
    - poetry run ruff check tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py
    - poetry run ruff format --check tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py
    - poetry run python -c "from scripts.validate_specs import extract_front_matter, task_files; active=sorted(str(extract_front_matter(path).get('id')) for path in task_files() if extract_front_matter(path).get('status') == 'active'); assert active == ['TASK-056'], active"
    - >-
      poetry run python -c "import fnmatch, subprocess; from pathlib import Path; from scripts.validate_specs import extract_front_matter; planning='0d9f8e879b2029c23ba955364080667d2efa50ed'; base=subprocess.check_output(['git', 'merge-base', 'origin/main', 'HEAD'], text=True).strip(); assert subprocess.run(['git', 'merge-base', '--is-ancestor', planning, base]).returncode == 0, {'planning_base': planning, 'implementation_base': base}; task=extract_front_matter(Path('tasks/active/TASK-056-codex-cline-collaboration.md')); changed=set(subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', base + '...HEAD'], text=True).splitlines()); allowed=set(task['allowed_paths']); forbidden=task['forbidden_paths']; outside=sorted(changed - allowed); blocked=sorted(path for path in changed if any(fnmatch.fnmatchcase(path, pattern) for pattern in forbidden)); assert not outside and not blocked, {'implementation_base': base, 'outside_allowed_paths': outside, 'forbidden_paths': blocked}; print({'implementation_base': base, 'changed_paths': sorted(changed), 'outside_allowed_paths': outside, 'forbidden_paths': blocked})"
    - git diff --check origin/main...HEAD
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
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

## Codex Implementation Plan

- Plan version: `TASK-056-PLAN-v2`
- Planning base SHA: `0d9f8e879b2029c23ba955364080667d2efa50ed`
- Observable outcome: Cline 从 GitHub 上的唯一 active task 获取 Codex Plan，基于其精确
  Implementation Base SHA 实现并提交 PR；新的 Codex Review 会话只读审查精确 Head；
  人类完成 merge 和 closeout 授权。

### Base identity decisions

- `Planning base SHA` 仅标识 Codex 形成和评审本 Plan 时所依据的 `main`；它必须是
  Implementation Base 的祖先，但不得与 Implementation Base 做相等比较。
- `Implementation Base SHA` 在 Activation PR 合并后解析：Cline 必须先 fetch，然后从当时
  的 `origin/main` 创建实现分支，并在任何修改前记录 `git rev-parse origin/main` 的精确值。
- 实现期间 `Implementation Base SHA` 不得漂移。最终验证必须以
  `git merge-base origin/main HEAD` 重算分支点、与修改前记录值比较，并以该精确 SHA 为 diff
  左端；同时确认 `git merge-base --is-ancestor <Planning Base SHA>
  <Implementation Base SHA>` 成功。
- Cline 必须在 Implementation Report 中分别报告两个 SHA；Planning Base 不是实现分支点，
  Activation PR 合并后两者不同是预期行为，不构成 `PLAN_BLOCKED`。

### Authority and role decisions

- `AGENTS.md`、`spec/manifest.yaml`、唯一 active task 和全部 `spec_refs` 仍是共同权威链。
- `.clinerules/` 只提供 Cline 工具入口和跨服务器交接约束，不复制业务契约正文。
- Codex 负责选任务、规范/架构分析、设计、测试拆解、冲突判断和 Review，默认不写实现。
- Cline 负责测试先行、最小实现、验证、commit、push 和 Implementation PR；不得自行改变
  设计、task、spec、激活状态、Review 结论、merge 或 closeout。
- 人类拥有任务激活、GitHub merge、branch protection 和任务完成状态迁移权限。

### File-level change plan

- `AGENTS.md`: 增加持久角色边界和 GitHub 精确 SHA 交接规则，只引用既有权威来源。
- `.clinerules/10-codex-handoff.md`: 定义 Base 校验、dirty worktree、`PLAN_BLOCKED`、PR
  evidence、禁止直接 push main/self-approve/merge/closeout。
- `ai/adapters/cline.md`: 要求 Cline 读取 task 内 Codex Plan，并输出标准 Implementation Report。
- `ai/workflows/team-collaboration.md`: 定义 Implementation Packet、Implementation Report、
  Repair Packet、精确 Head Review，以及 Implementation/Closeout 两个 PR 生命周期。
- `tasks/templates/task-template.md`: 增加非规范性的版本化 Codex Implementation Plan 模板。
- `tests/spec/test_codex_cline_collaboration_governance.py`: 机器锁定上述治理要求。
- `tests/spec/test_miniqmt_m1_delivery_governance.py`: 只同步 TASK-056 active 占用断言，保留
  TASK-054/055、MiniQMT 和 TASK-053 全部安全断言。

### Acceptance-to-test mapping

- Authority chain、无 active、Planning/Implementation Base、dirty/plan gap fail-closed → Cline
  rule/adapter 文本测试。
- 三角色边界、三类交接物、两 PR 生命周期和精确 SHA → team workflow 文本测试。
- 后续 task 必须携带 Plan version/Base/design/test/failure/stop fields → task template 测试。
- TASK-056 唯一 active、054/055 completed、053 blocked → task/index/active README 投影测试。
- 禁止业务路径和规范变更 → verification 中的 changed-path membership 命令必须读取当前
  task 的 `allowed_paths`/`forbidden_paths`，并对
  `git diff --name-only --no-renames <Implementation Base SHA>...HEAD` 的每个路径执行成员资格
  检查；越权、命中 forbidden、无法确定 Base 或无法解析 task 时审计必须失败。

### Failure, concurrency, and recovery design

- Planning Base 不是 Implementation Base 祖先、当前分支不是从记录的 Implementation Base
  创建、工作区有非预期修改、active task 数量不为一、task/spec 冲突、allowed paths 不足
  或设计缺口时，Cline 必须停止并返回 `PLAN_BLOCKED` 及证据。
- Cline 不得用 force-push、直接 push main、降低测试或自行修改 task/spec 解决阻塞。
- Codex Review 必须绑定精确 Head；Head 改变后旧 APPROVE 失效并重新 Review。
- Implementation PR 合并不等于 task completed；必须另建 Closeout PR 核验 Review、CI、
  merge 和人类授权。任何外部事实不可核验时保持 pending/prohibited。

### Implementation order

1. 先新增失败的协作治理测试，并确认只因预期规则尚未实现而失败。
2. 更新 AGENTS、Cline handoff、adapter、team workflow 和 task template 的最小文本。
3. 运行全部 verification commands；其中 changed-path 命令必须重算并输出精确的
   Implementation Base SHA，以其为左端完成 exact allowed/forbidden path audit，并由 Cline
   将输出值与修改前记录值比较。
4. Cline 推送 Implementation PR，报告 Base/Head、changed files、acceptance、commands、
   unverified scope、risks 和 spec deviations；不得合并或移动任务。
5. 新 Codex Review 会话对精确 Head 输出 `APPROVE`、`REQUEST_CHANGES` 或 `BLOCKED`。

### PLAN_BLOCKED conditions

- 规范或 Accepted ADR 与本 Plan 冲突。
- 必须修改 forbidden path、业务契约、CI、依赖或 GitHub 权限才能完成。
- Planning Base 已不再是 Implementation Base 祖先、Implementation Base 与修改前记录值
  不一致，或 active task/任务依赖状态发生变化。
- 无法执行 verification commands，或 Cline 无法证明 diff 只覆盖 allowed paths。

## Non-goals

- 不修改任何业务代码、规范、migration、依赖、CI、交易配置或 GitHub 权限。
- 不激活、实施或改变 TASK-053、TASK-052、TASK-048 及其依赖或 acceptance。
- 不创建同名 `.clinerules` 单文件，不把 `.clinerules/` 变成平行 `spec/`。
- 不声称文本规则能够替代 CI、branch protection、独立 Review 或人类 merge。

## Deliverables

- 项目级 Codex/Cline 职责和 GitHub 事实交接规则。
- Cline 固定 handoff 约束和标准 Implementation Report。
- 三类交接物、两 PR 生命周期及 Repair 循环的工具中立工作流。
- 可复用的 task-level Codex Implementation Plan 模板。
- 覆盖角色隔离、精确 SHA、fail-closed 和队列投影的机器治理测试。

## Acceptance criteria

- [ ] 持久规则明确 Codex 决策、Cline 产能、Codex 独立验收、人类最终授权的角色边界。
- [ ] Cline 必须读取 Codex Plan，并在无 active、Base 不匹配、dirty 或设计缺口时 fail-closed。
- [ ] `.clinerules/` 只引用 AGENTS/task/spec，不复制 Event、DTO、状态机或错误码契约。
- [ ] Cline Report 包含 Base/Head SHA、branch/PR、changed files、逐项 acceptance、命令退出码、
  未验证范围、风险、spec deviations 和 allowed-path diff 结论。
- [ ] Codex Review 绑定精确 Head，结论仅为 APPROVE、REQUEST_CHANGES 或 BLOCKED；Head 改变
  后必须重新 Review。
- [ ] Implementation PR 与 Closeout PR 分离；Cline 不得 self-approve/merge/closeout。
- [ ] Task template 明确区分 Planning Base SHA 与 Activation 合并后记录的 Implementation
  Base SHA，并包含设计、文件计划、测试映射、失败设计和 PLAN_BLOCKED 条件。
- [ ] 没有修改 spec、业务代码、migration、依赖、CI、交易权限或现有任务 scope。
- [ ] changed-path membership audit 和所有 verification commands 通过，独立 Review
  后才可进入 closeout。

## Required evidence

- 使用 `ai/workflows/implement-task.md` 格式报告 changed files、逐项 acceptance、命令与
  exit code、未验证范围、风险和 spec deviations。
- Implementation Report 分别记录 Planning Base SHA、exact Implementation Base/Head、
  branch/PR，以及以 Implementation Base 为左端的完整 allowed/forbidden-path audit。
- Closeout 记录独立 Review、CI、merge commit 和人类授权；未知事实不得猜测。

## Risks and rollback

- 本地模型可能不遵守文本规则；实际门禁仍依赖 task validator、CI、精确 diff、独立
  Review、branch protection 与人类 merge。
- 过度复制规范会造成漂移；工具规则只允许指向权威来源。
- 回滚只恢复本任务产生的协作规则、模板、测试和任务投影，不影响业务代码或运行状态。
