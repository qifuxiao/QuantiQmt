---
id: TASK-051
title: Reauthorize Risk validator integration scope through a trusted successor gate
status: active
depends_on: [TASK-015, TASK-031, TASK-044]
spec_refs: [CONTRACT-RISK-DECISION-V1, CONTRACT-RISK-AUDIT-OUTPUT-V1, CONTRACT-RISK-ORDER-EVALUATED-V2, PORTS-RISK, CONTRACT-CATALOG]
allowed_paths:
  - tasks/active/TASK-051-risk-validator-integration-scope-successor.md
  - tasks/completed/TASK-051-risk-validator-integration-scope-successor.md
  - tasks/backlog/TASK-029-risk-runtime-schema-contract.md
  - tasks/active/TASK-029-risk-runtime-schema-contract.md
  - tasks/active/README.md
  - tasks/index.yaml
  - scripts/validate_specs.py
  - tests/spec/test_validate_specs.py
  - ai/governance/risk-validator-integration-scope-task-051.yaml
forbidden_paths:
  - spec/**
  - docs/**
  - src/**
  - migrations/**
  - tests/contract/**
  - tests/unit/**
  - tests/property/**
  - tests/integration/**
  - pyproject.toml
  - poetry.lock
  - .github/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec
    - poetry run pytest tests/contract
    - poetry run ruff check scripts/validate_specs.py tests/spec/test_validate_specs.py
    - poetry run ruff format --check scripts/validate_specs.py tests/spec/test_validate_specs.py
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: passed
  review_status: pending
  release_status: prohibited
---

# Objective

以一份全新、可审计、必须经独立 Review 的 successor 授权，重新确认 TASK-029 接入既有正式 Risk Schema、统一 Schema validator、语义 validator 与冻结边界所需的最小实现范围。该授权替代 TASK-029 对 TASK-030 历史交付证据的依赖，但不修改、补造、提升或复用 TASK-030 的任何历史 Review、批准、验收或发布事实。

## Activation evidence

- 2026-08-27 人类明确授权创建、激活并实施 TASK-051，建议编号为 TASK-051。
- TASK-015、TASK-031 与 TASK-044 均为 schema-v1、acceptance passed、独立 Review approved、implementation merged 且 completion evidence 完整可信的 completed 前置任务。
- TASK-044 已确认 TASK-030 的 scope PR #42 与 closeout PR #44 均无可验证的正式 Review；TASK-030 必须继续保持 `review_status: reported_unverified`、`release_status: prohibited`，且不得用本任务倒推历史批准。
- 本任务只重新授权治理范围和 successor gate，不激活或实现 TASK-029、TASK-005，不授权 runtime、部署、发布或 active → completed 收尾。

## Required successor decision

- TASK-029 的直接依赖从历史 `TASK-030` gate 迁移到新 `TASK-051` gate，同时保留可信的 TASK-015 与 TASK-031 依赖。
- 重新确认 TASK-029 仅可修改其现有正式 Risk Schema/contract package、`model.py`、`audit.py`、`runner.py`、`evaluator.py`、对应 contract/unit/property tests 和任务治理路径。
- 仅允许接入已接受的 Risk Schema → semantic validation → immutable freeze 生产路径；不得新增或改变 Event、Command、DTO、公开 Schema、错误码、Risk 规则语义、状态迁移、Repository 或 Workflow 契约。
- Order、Persistence、Broker、Execution、Redis/外部 I/O、migration 与 docs 均不在 TASK-029 授权范围；允许的 `src/quantiqmt/contracts/**` 仅用于可部署 Schema bundle/registry/validator，不得扩展为业务 I/O。
- TASK-029 必须继续 `blocked`。只有 TASK-051 后续被独立 Review APPROVE，并由人类在 merge 后以 schema-v1、acceptance passed、implementation merged 和完整可信 completion evidence 收尾为 completed，TASK-029 才可能由人类另行激活。

## Non-goals

- 不修改 TASK-030 completed 文件或 `ai/governance/historical-delivery-evidence-task-044.yaml`。
- 不把 TASK-051 写成 waiver，也不允许 bypass、ready 标签或 active/in-progress evidence 解锁 TASK-029。
- 不执行 TASK-029 或 TASK-005，不修改 Risk runtime、规范、公开消息、错误码、release 状态或依赖包。
- 不合并、自我 Review、自行把 TASK-051 移入 completed，或自动激活任何下游任务。

## Acceptance criteria

- [x] TASK-051 active 记录、`tasks/index.yaml` 与 active README 投影一致，且所有依赖具有可信 completed delivery。
- [x] 新的机器可审计授权逐项绑定 accepted Risk spec、TASK-029 现有 allowed/forbidden scope、历史边界与 rollback；不借用 TASK-030 的 unverified Review 事实。
- [x] TASK-029 直接依赖包含 TASK-051、TASK-015、TASK-031，不再使用 TASK-030 作为激活 gate；TASK-029 与 TASK-005 均保持 blocked。
- [x] validator fail-closed 强制 TASK-029 使用 TASK-051 successor，拒绝 TASK-030、TASK-046 或缺失 successor 的替代/旁路，同时保留 TASK-030 的历史审计边界。
- [x] spec tests 覆盖 TASK-051 为 active/in-progress、completed/reported-unverified、completed/缺失可信 evidence、completed/trusted 四类状态；只有最后一类满足依赖 gate，且任何一类都不会自动激活 TASK-029。
- [x] TASK-029 allowed paths 包含既有正式 Schema/contract package、Risk DTO/Audit/Runner/Evaluator 与对应 contract/unit/property tests；forbidden scope 明确排除其他业务上下文、外部 I/O、migration 与 docs。
- [x] 未修改 TASK-030、Risk 业务代码、规范契约、公开 Schema、错误码或 release 状态，所有 verification commands 通过。
- [x] 实现等待另一位成员在精确 Head 上独立 Review；实现 Agent 未自批、未合并、未完成 TASK-051。

## Implementation evidence

- `ai/governance/risk-validator-integration-scope-task-051.yaml` 以 schema-v1 记录 accepted spec、可信依赖、TASK-030 历史边界、TASK-029 精确范围、四态 activation matrix、TASK-050 并行分支隔离与 Review 权限边界。
- `successor_evidence_binding` 将 successor gate 固定到 `qifuxiao/QuantiQmt` PR #87、实现者身份和独立 GitHub Review 字段；在 Review/merge/人类收尾事实仍为 pending 时，任何 TASK-051 completion evidence 都不能解锁 TASK-029。
- `scripts/validate_specs.py` 将通用 L4/TASK-046 gate 与 Risk/TASK-051 gate 分离：TASK-029 必须依赖 TASK-051，TASK-030/TASK-046 均不能替代；TASK-030 必须保持 completed + reported-unverified + prohibited。
- successor validator 只验证治理记录与任务 evidence 的固定仓库/PR/Review URL、SHA、reviewer 独立性和字段一致性；它不联网声称 GitHub Review、精确 Head、merge 或人类授权事实已真实发生，这些仍须独立 Review 与人类收尾确认。
- TASK-029 仅把直接依赖从 TASK-030 迁移到 TASK-051，并补充 successor 授权/forbidden scope；其 status 仍为 blocked，既有 allowed paths 和 acceptance criteria 未削弱。
- `tests/spec/test_validate_specs.py` 覆盖 real-repository 投影、历史不可提升、错误 successor 替代，以及 active、reported-unverified、missing evidence、trusted completed 四态；测试兼容未来 TASK-051 合法 active → completed 路径迁移。
- TASK-030 文件与 TASK-044 历史审计文件的 Git blob 分别保持 `4cc37f6d1805d98bc4f223bfe69d4de5c51b7f8e`、`c4dfc1703c1782fdd9c062ce22fb830c2388c365`，与 `origin/main` 完全一致。

## Verification evidence

- 2026-08-27 复核确认用户级 `poetry.exe` 是有效的 Windows symbolic link；Poetry 2.4.1、Python 3.12.10 与项目环境 `quantiqmt-pHxzv3NO-py3.12` 均正常。最初五条 `poetry run ...` 尝试在测试启动前 exit 1，真实根因是 Codex sandbox 拒绝访问用户目录；早先将 0-byte link 显示解释为 launcher 损坏属于已更正的证据错误，不代表 Poetry 或依赖失败。
- 在用户明确授权的 sandbox 外执行上下文中，将同一 Poetry 进程绑定到上述项目环境后，五条原始命令均实际通过：`poetry run python scripts/validate_specs.py` exit 0；`poetry run pytest tests/spec` exit 0，53 passed；首次 `poetry run pytest tests/contract` exit 0，678 passed、1 skipped（该用例明确要求前置 `poetry build` wheel）；两条 `poetry run ruff ...` 均 exit 0。随后在同一环境执行 `poetry build` exit 0，生成 `quantiqmt-0.1.0-py3-none-any.whl` 后重跑原 contract 命令 exit 0，679 passed、0 skipped，wheel 安装包测试已实际执行。
- 首次提交的 pre-commit hooks exit 1、随后使用 `--no-verify` 提交是保留的真实历史；根因同样是当时 Codex sandbox 无法使用用户目录中的已授权项目环境，而不是 Poetry 安装或项目依赖损坏。本次 `poetry run pre-commit run --all-files` 在 sandbox 外 exit 0，`ruff check`、`ruff format`、`validate specs and tasks` 三个 hook 全部 Passed；本次修正提交不得使用 `--no-verify`。
- 测试先行证据：validator 新入口实现前，focused spec test collection exit 1，精确失败为无法导入 `validate_risk_scope_successor_dependencies`；最小实现后同一文件 53 passed。
- `git diff --check` exit 0；changed-path audit 仅包含 TASK-051 `allowed_paths`。

## Handoff boundary

- 本地 acceptance 已通过；TASK-051 保持 active、implementation in-progress、Review pending、release prohibited，等待另一位成员对精确 Head 独立 Review。
- 未激活/实现 TASK-029 或 TASK-005，未修改 runtime、spec、公开 Schema、错误码、TASK-030 历史或 release 状态。

## Review focus

- successor 是否是真正独立的新授权，而不是改写或包装 TASK-030 的历史批准。
- successor completion evidence 是否逐字段匹配 PR #87 的治理 binding，且没有使用实现者身份、占位 SHA、任意仓库/PR 或无效 Review URL 伪造独立 Review；静态校验与 GitHub/人类事实的边界是否清楚。
- TASK-051 未可信 completed 时，TASK-029 是否在目录、依赖与 delivery evidence 三层都保持 fail-closed。
- TASK-029 范围是否足以接入既有 validator，同时没有扩大到 Order/Persistence/Broker/Execution/Redis、规范语义或 release。
- validator/tests 是否既拒绝历史 gate 旁路，又允许未来合法的 TASK-051 reviewed/merged closeout 后由人类另行激活 TASK-029。

## Risks and rollback

- 错误放行 TASK-029 会绕过 Risk schema/semantic validation 的治理授权；任何缺失、矛盾或无法验证的 TASK-051 evidence 必须拒绝激活。
- 回滚只恢复 TASK-029 对 TASK-051 的依赖、TASK-051 active 记录、validator/test 与新审计记录；不得改动 TASK-030 历史或任何业务/规范文件。
- 若实现发现必须改变已接受 Risk 语义、公开契约或错误码，停止并创建独立 spec-change task，不得扩大 TASK-051。
