---
id: TASK-053
title: Resolve TASK-052 and TASK-048 dependency sequencing deadlock
status: active
depends_on: [TASK-031, TASK-043, TASK-049, TASK-050]
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - tasks/backlog/TASK-053-dependency-sequencing-governance.md
  - tasks/active/TASK-053-dependency-sequencing-governance.md
  - tasks/completed/TASK-053-dependency-sequencing-governance.md
  - tasks/backlog/TASK-052-task-004-delivery-revalidation.md
  - tasks/active/TASK-052-task-004-delivery-revalidation.md
  - tasks/backlog/TASK-048-order-registration-broker-capability-binding.md
  - tasks/active/README.md
  - tasks/completed/README.md
  - tasks/index.yaml
forbidden_paths:
  - src/**
  - spec/**
  - migrations/**
  - tests/**
  - scripts/**
  - .github/**
  - docs/**
  - pyproject.toml
  - poetry.lock
  - tasks/completed/TASK-004-persistence-outbox.md
  - tasks/active/TASK-048-order-registration-broker-capability-binding.md
  - tasks/completed/TASK-048-order-registration-broker-capability-binding.md
  - tasks/completed/TASK-052-task-004-delivery-revalidation.md
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_order_registration_binding_contracts.py
    - poetry run python -c "from scripts.validate_specs import extract_front_matter, task_files; active=sorted(str(extract_front_matter(path).get('id')) for path in task_files() if extract_front_matter(path).get('status') == 'active'); assert active == ['TASK-053'], active"
    - poetry run python -c "from pathlib import Path; from scripts.validate_specs import extract_front_matter; root=Path('tasks'); t052=extract_front_matter(root/'backlog'/'TASK-052-task-004-delivery-revalidation.md'); t048=extract_front_matter(root/'backlog'/'TASK-048-order-registration-broker-capability-binding.md'); t004=extract_front_matter(root/'completed'/'TASK-004-persistence-outbox.md'); assert t052['status']=='blocked'; assert t048['status']=='blocked'; d=t004['delivery']; assert d['acceptance_status']=='unverified' and d['review_status']=='reported_unverified' and d['release_status']=='prohibited'"
    - poetry run python -c "import fnmatch, subprocess; from pathlib import Path; from scripts.validate_specs import extract_front_matter; task=extract_front_matter(Path('tasks/active/TASK-053-dependency-sequencing-governance.md')); changed=subprocess.check_output(['git','diff','--name-only','origin/main...HEAD'], text=True).splitlines(); unauthorized=[p for p in changed if not any(fnmatch.fnmatchcase(p, pattern) for pattern in task['allowed_paths'])]; forbidden=[p for p in changed if any(fnmatch.fnmatchcase(p, pattern) for pattern in task['forbidden_paths'])]; assert not unauthorized, unauthorized; assert not forbidden, forbidden"
    - git diff --check origin/main...HEAD
    - git diff --name-only origin/main...HEAD
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

以 fail-closed 的治理顺序解除 TASK-052 与 TASK-048 的 sequencing deadlock，不修改
任何业务实现、规范、migration、业务测试、CI、依赖文件、运行时或部署发布资产。

TASK-052 已确认当前 Spec 0.14 broker binding、`002` migration 与对应测试缺口阻断
TASK-004 revalidation；TASK-048 定义该 remediation，却直接依赖 TASK-004 的可信
delivery，而 TASK-004 正等待 TASK-052 revalidation。该循环是治理排序问题，不是
伪造完成证据、降低 acceptance 或创建 waiver 的理由。

## Human authorization

- 2026-08-28 人类明确授权：“授权创建并激活 TASK-053 dependency sequencing 治理
  任务，仅解决 TASK-052 与 TASK-048 的依赖顺序，不修改业务实现。”
- 授权范围仅包括现状审计、TASK-053 激活、TASK-052 暂停投影，以及后续在本任务
  精确 allowed paths 内审计并受控修正 TASK-048 task metadata 或记录明确的
  remediation successor 方案。
- 本授权不覆盖 TASK-048 业务 remediation、TASK-004 delivery 升级、waiver、
  TASK-048/TASK-052 自动激活、部署、发布、自审、批准或 merge。

## Activation evidence and occupancy audit

- 本任务从 2026-08-28 fetch 后的最新 `origin/main`
  `c3816482f207b985a6c704a66c6c0e0a07f3632d` 创建；该提交是 PR #89 merge commit，
  并包含 TASK-052 activation head
  `5f193755bb03d70fe294c80b30a8a882693a74f2`。
- PR #89 author 为 `qfxyyy`。不同作者的 OWNER reviewer `qifuxiao` 对精确 activation
  head 提交正式 `APPROVED` Review，`commit_id` 与 head 相同：
  https://github.com/qifuxiao/QuantiQmt/pull/89#pullrequestreview-5048291488
- PR #89 的精确 head 有 4/4 GitHub CI checks successful，并已合并为上述 merge
  commit。该证据只证明 TASK-052 activation PR 可信，不证明 TASK-004 revalidation、
  PostgreSQL 16 acceptance 或 Spec 0.14 remediation 已完成。
- 创建前检查 worktree clean；TASK-053 在 `origin/main`、已 fetch 的远端 refs、
  `tasks/index.yaml`、`tasks/active/`、`tasks/backlog/`、`tasks/completed/` 中均未占用。

## Frozen sequencing decision

1. 本激活 PR 将 TASK-052 从 `tasks/active/` 暂停至 `tasks/backlog/`，状态改为
   `blocked`；TASK-053 成为唯一 active task。TASK-052 的五轴 delivery 保持
   `not_started/not_run/pending/prohibited`，不得伪装为完成。
2. TASK-053 后续只审计 TASK-048 的 `depends_on` 是否把“当前 persistence 基线”
   错误表达成“必须先有 TASK-004 可信历史 delivery”。审计必须选择且记录一个
   fail-closed 结果：
   - 若证据足够，只允许精确修正 TASK-048 的依赖/任务元数据，保留 TASK-017 与
     TASK-050 的可信门禁以及全部业务 scope、acceptance、binding/UNBOUND 安全边界；
   - 若证据不足，TASK-048 保持原样 blocked，只在 TASK-053 正文中记录一个具有
     精确职责、依赖和独立授权要求的 remediation successor 方案；不得自行创建、
     激活或实施该 successor。
3. TASK-048 metadata 不得在本激活 PR 中顺带修改。任何后续 correction 必须属于
   TASK-053 的单独实施 Head，并经独立 Review、CI 与人类 merge。
4. TASK-053 治理实现可信合并后，仍不得自动激活 TASK-048。人类只能另行激活
   TASK-048，或另行授权并激活审计选择的精确 remediation task。
5. remediation 业务实现完成、独立 Review、CI 与 merge 可信后，才可由人类重新
   激活 TASK-052，并在隔离 PostgreSQL 16 环境执行完整 revalidation。
6. 任一阶段都不得自动把 TASK-004 的 `unverified/reported_unverified` 改为
   `passed/approved`，不得创建 waiver，不得把 PR #89 当作 TASK-004 completion
   evidence，不得部署或发布。

## Non-goals

- 不实现或修改 TASK-048 的 runtime DTO、serialization、Memory/PostgreSQL adapter、
  `002` migration 或任何 business test。
- 不修改 `src/**`、`spec/**`、`migrations/**`、`tests/**`、`scripts/**`、CI、依赖、
  lockfile、运行时、部署或发布文件。
- 不改变 Event、Command、DTO、错误码、状态迁移、Repository 或 Workflow 契约。
- 不修改 TASK-004 delivery，不完成 TASK-052，不自动激活 TASK-048/TASK-052 或任何
  下游任务。
- 不自审、approve 或 merge TASK-053 的任何 PR。

## Deliverables

- 本激活 PR：TASK-053 active task、TASK-052 backlog/blocked 暂停投影、唯一 active
  README 与 `tasks/index.yaml` 一致性；不修改 TASK-048。
- 后续 TASK-053 实施 PR：TASK-048 依赖语义审计及上述二选一治理决策，只使用精确
  allowed paths，并记录 exact Base/Head、changed paths、验证、独立 Review 与 merge
  证据。
- 明确后续手工门禁：治理合并 → 人类激活精确 remediation → remediation 可信合并
  → 人类重新激活 TASK-052 → PostgreSQL 16 revalidation。

## Acceptance criteria

- [ ] TASK-048 的 TASK-004 dependency 已被逐项审计，结论明确区分当前代码基线、
  历史 delivery trust 与 remediation unlock，不形成新循环或降低可信门禁。
- [ ] 只选择 Frozen sequencing decision 中一个结果：精确修正 TASK-048 task
  metadata，或保持 TASK-048 不变并记录需另行授权的精确 successor 方案。
- [ ] 若修正 TASK-048，只改变依赖/任务元数据；TASK-017、TASK-050、全部业务
  acceptance、allowed/forbidden paths、BOUND/UNBOUND 与 no-rebinding 边界保持。
- [ ] TASK-053 是唯一 active task；TASK-052 为 backlog/blocked，TASK-048 仍为
  backlog/blocked 且未自动激活，目录/status/index/active README 完全一致。
- [ ] TASK-004 保持 `acceptance_status: unverified`、
  `review_status: reported_unverified`、`release_status: prohibited`，没有 waiver、
  inferred approval 或 activation PR 证据替代。
- [ ] 没有修改任何业务实现、规范、migration、现有测试、validator、CI、依赖、
  runtime、部署或发布文件；exact allowed/forbidden path audit 通过。
- [ ] TASK-053 实施 Head 的所有 verification commands 与 CI 通过，并获得不同作者的
  独立正式 `APPROVED` Review；实现 Agent 不自审、不 approve、不 merge。
- [ ] 治理 closeout 只给后续人类激活精确 remediation 提供输入，不自动激活任何
  task；release 保持 prohibited。

## Required evidence

- 使用 `ai/workflows/implement-task.md` 格式记录 task、spec refs、changed files、
  逐项 acceptance、命令与退出码、未验证范围、风险及 spec deviations。
- 记录 TASK-052/TASK-048/TASK-004 的 exact queue/delivery state、dependency graph、
  选择修正或 successor 方案的证据与反例。
- 记录 exact Base/Head、PR、CI、独立 Review verdict/reviewer/evidence URL、merge commit
  与人类授权；无法验证的事实保持 `unverifiable`。
- 保存唯一 active、索引/目录、blocked 状态、TASK-004 delivery 与 exact path audit
  命令的输出和退出码。

## Review focus

- 是否真正解除排序循环，而没有把不可信 TASK-004 历史 delivery 伪装成已验证。
- 是否保留 TASK-048 的 Spec 0.14 BOUND/UNBOUND、no-rebinding、expand-only migration
  与 fail-closed 安全边界。
- 是否严格分离治理 correction、业务 remediation、TASK-052 revalidation 与发布。
- 是否存在越权业务路径、自动激活、waiver、self-review 或 release 状态提升。

## Risks and rollback

- 错误删除真实语义依赖可能让 remediation 在不安全基线上执行；证据不足时必须选择
  successor 方案并保持 TASK-048 blocked。
- 回滚仅恢复 TASK-053/TASK-052 的任务队列投影与 TASK-048 治理 metadata，不得改动
  TASK-004 delivery、业务代码、规范、migration、数据库、Journal、Snapshot 或
  Outbox 历史。
- 任何目录/status/index/README 不一致、路径越权、依赖冲突或证据缺失都必须 fail
  closed，保持 TASK-052/TASK-048 blocked 且 release prohibited。
