---
id: TASK-047
title: Make the L4 successor dependency spec test location-aware
status: active
depends_on: [TASK-046]
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.7]
allowed_paths:
  - tests/spec/test_validate_specs.py
  - tasks/active/TASK-047-l4-successor-test-location-awareness.md
  - tasks/active/README.md
  - tasks/index.yaml
forbidden_paths:
  - spec/**
  - src/**
  - scripts/**
  - tasks/backlog/**
  - tasks/completed/**
  - tasks/governance-waivers.yaml
  - tests/contract/**
  - tests/unit/**
  - tests/property/**
  - tests/integration/**
  - migrations/**
  - docs/**
  - pyproject.toml
  - poetry.lock
  - .github/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: passed
  review_status: pending
  release_status: prohibited
---

# Objective

修复 L4 successor dependency spec test 对 `tasks/backlog/` 的路径硬编码，使 TASK-017/018/019/020/021/022 在合法队列状态迁移后仍能验证 TASK-046 successor 依赖，不阻断人类授权的 backlog → active 激活流程。

## Scope and deliverables

- 只修改 `tests/spec/test_validate_specs.py` 中定位 L4 successor task 文件的测试逻辑。
- 从 `tasks/index.yaml` 的权威 path 或等价的队列感知方式解析 TASK-017/018/019/020/021/022，而不是假定这些任务永久位于 `tasks/backlog/`。
- 保持 TASK-046 successor dependency 断言及 TASK-029/TASK-030 独立阻断断言不变。

## Non-goals

- 不修改 `scripts/validate_specs.py`。
- 不修改任何业务代码、L4 契约、Schema、接口、工作流、错误码或状态机。
- 不激活 TASK-017 或任何其他 L4/业务任务。
- 不修改 TASK-046、TASK-014、TASK-030、waiver 或 completed 历史。

## Acceptance criteria

- [x] `test_l4_queue_uses_task046_successor_without_rewriting_task029_gate` 不再将 TASK-017/018/019/020/021/022 硬编码到 `tasks/backlog/`。
- [x] 测试从权威队列元数据解析任务路径，并继续断言六个 successor task 依赖 TASK-046 且不依赖 TASK-014。
- [x] TASK-029 仍必须依赖 TASK-030，且不得以 TASK-046 替代。
- [x] 测试覆盖至少一个 successor task 位于 `tasks/active/` 时的路径解析，证明合法激活不会导致 `FileNotFoundError`。
- [x] 不得通过跳过测试、吞掉路径解析异常或复制任务文件制造通过；缺失、重复或不一致的任务路径仍须 fail-closed。
- [x] `poetry run python scripts/validate_specs.py` 与 `poetry run pytest tests/spec tests/contract` 全部通过。
- [x] changed-path 审计仅包含 TASK-047 allowed paths，且未触及任何 forbidden path。

## Implementation evidence pending independent Review

- Implementation base is `main@e27df973fd512540a7a4a0885a661d71591f0180`; branch is `codex/task-047-implementation`.
- The real-repository successor dependency test resolves TASK-017/018/019/020/021/022 and TASK-029 through each unique `tasks/index.yaml` path instead of assuming `tasks/backlog/`.
- A minimal synthetic fixture proves `active/TASK-017.md` resolution without copying the real TASK-017 file.
- Missing index entries, duplicate index entries, missing indexed files and mismatched task IDs each fail with `AssertionError`; no test is skipped and no exception is swallowed.
- `poetry run python scripts/validate_specs.py` passed; `poetry run pytest tests/spec tests/contract` passed with 234 tests.
- Only this active TASK-047 record and `tests/spec/test_validate_specs.py` changed. TASK-017 remains backlog/ready; no specification, validator, runtime, completed-history or waiver file changed.
- No approval, merge, completion evidence, release eligibility or active-to-completed transition is claimed by the implementing Agent.

## Independent Review focus

- 修复是否仅消除目录位置假设，而没有削弱 TASK-046/TASK-014/TASK-029/TASK-030 的依赖断言。
- 测试是否真正覆盖 active 路径，而非通过跳过、捕获异常或复制任务文件制造通过。
- 是否未修改 validator、规范、业务代码或其他任务状态。

## Risks and rollback

- 若路径解析脱离 `tasks/index.yaml` 或实际队列状态，测试可能掩盖 index/file drift；必须继续由 validator 的目录、状态和 index 一致性检查 fail-closed。
- 回滚仅恢复本任务对 spec test 的最小修改及 TASK-047 治理记录，不得恢复 backlog 路径硬编码后继续激活 L4 task。
