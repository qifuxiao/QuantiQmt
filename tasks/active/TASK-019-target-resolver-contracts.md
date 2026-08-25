---
id: TASK-019
title: Complete Target Resolver L4 contracts
status: active
depends_on: [TASK-046, TASK-016, TASK-018]
spec_refs: [INV-TRADING, INV-RISK, PORTS-STRATEGY, PORTS-LEDGER-PORTFOLIO, PORTS-MARKET, CONTRACT-STRATEGY-TARGET-V1, CONTRACT-ORDER-INTENT-V1, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-PORTFOLIO-PROJECTION-V1, SM-ORDER, STORAGE-OUTBOX, CONTRACT-TARGET-RESOLVER-V1, CONTRACT-TARGET-RESOLVER-SEMANTIC-V1, WF-TARGET-RESOLUTION, STORAGE-TARGET-RESOLUTION]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/storage/**, tests/contract/messages/**, tasks/backlog/TASK-009-target-resolver.md, tasks/backlog/TASK-019-target-resolver-contracts.md, tasks/active/TASK-019-target-resolver-contracts.md, tasks/active/README.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/unit/**, tests/property/**, tests/integration/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: draft
  implementation_status: in_progress
  acceptance_status: partial
  review_status: pending
  release_status: prohibited
---

# Objective

冻结 TargetWeight/TargetPosition 到 OrderIntent 的确定性转换契约，包括 InstrumentSpec、price reference、rounding、active order effect、mandate/scope 和 idempotency。

## Activation evidence

- 2026-08-24 人类明确批准激活并实施 TASK-019；该授权仅增加本任务 active 路径与 `tasks/active/README.md` 到 allowed paths，并执行 backlog → active 队列迁移。
- 直接依赖 TASK-046、TASK-016、TASK-018 均为 completed，且各自具有可信独立 Review、精确 reviewed head 与 merge commit 证据。
- 本次激活不授权运行时代码、迁移、发布、TASK-009 激活或 TASK-019 active → completed 收尾。

## Non-goals

- 不实现 TargetResolver。
- 不执行 Risk approve。
- 不访问 Broker 或 OMS Repository。

## Acceptance criteria

- [x] 定义 Target DTO、scope、strategy mandate、valid_until 和 replay semantics。
- [x] 定义 InstrumentSpec、lot/tick、min quantity、price band、cash buffer 和 deadband。
- [x] 定义 current position、strategy sleeve、portfolio snapshot 和 active order expected effect。
- [x] 定义 deterministic resolution id、intent_id/idempotency key 和 NoAction/Rejected reasons。
- [x] 更新 TASK-009，使其可直接实现。

## Implementation evidence

- `CONTRACT-TARGET-RESOLVER-V1` 与 Semantic Contract 冻结严格内部 DTO、RFC8785/SHA-256、UUIDv5 固定向量、Decimal-only 运算、封闭 outcome/reason/error 映射以及 Result/Outbox 审计绑定；公开 Target 与 OrderIntent V1 Payload Schema 未修改。
- Target replay 被拆为三个互不混淆的门禁：稳定 `target_id + target_fingerprint` 注册、Snapshot 前 `(target_id, trigger_message_id)` 去重、Snapshot 后 `input_fingerprint` 去重。同一有效 Target 可在新的可信 trigger 和新快照下再次解析；同输入只记录 replay receipt，不重复写 Outbox。
- trigger replay 与 Snapshot 之间增加 Intent→OMS handoff 门禁：同 account/scope/instrument 存在 Outbox pending 或 published-awaiting-OMS Intent 时，只记录 `HANDOFF_DEFERRED`，直到同 intent_id 的 OMS 注册证据和新的 ORDER_CHANGED trigger 到达，消除 Intent 已提交但 active-order Snapshot 尚不可见的重复下单窗口。
- Snapshot 契约绑定 Portfolio/Strategy sleeve/OMS trade watermark 与 Account reservation version，active order 绑定 original/cumulative/applied/leaves，防止部分成交双算、重复买入或重复卖出。无法构造完整可信 Snapshot 时记录无 resolution identity 的 `SNAPSHOT_REJECTED` 回执，禁止伪造快照。
- `WF-TARGET-RESOLUTION`、`STORAGE-TARGET-RESOLUTION` 与 `PORTS-STRATEGY` 冻结有界 deadline、append-only target/trigger/result、UNKNOWN 查询恢复、Resolution + 可选 OrderIntent Outbox 原子提交，以及 `OrderIntent → OMS 注册 → Risk → OMS 迁移 → Execution` 唯一路径。
- `tests/contract/messages/test_target_resolver_contracts.py` 提供可执行正负矩阵，覆盖 deterministic vector、三层 replay、部分成交/订单终态后重解析、active-order overlap、cash/availability、rounding、price band、stale/partial/identity、解析前失败和错误/投递状态绑定。
- TASK-009 已改为纯 Resolver + application orchestration 的直接实现边界，并明确仍等待 TASK-007、TASK-008、TASK-019 全部可信完成；本任务未激活 TASK-009。

## Deferred production boundary

- 本任务不实现 runtime、物理数据库、migration、生产 Outbox writer 或 StrategySleeveProjection provider。后续 TASK-009 仍只能交付纯计算/application Port；生产 journal/Outbox adapter、expand-only migration 和 sleeve attribution provider 必须由另外的人类授权任务交付，当前 release 保持 prohibited。

## Verification evidence

- `poetry run python scripts/validate_specs.py`：通过。
- `poetry run pytest tests/spec tests/contract`：`663 passed in 31.95s`。
- `poetry run pytest tests/contract/messages/test_target_resolver_contracts.py -q`：`41 passed`。
- `poetry run ruff check` 与 `poetry run ruff format --check`：TASK-019 涉及的三个契约测试文件全部通过。
- 以上为本地实现证据，不构成独立 Review、CI、merge 或 completed delivery evidence；delivery 继续保持 `draft/in_progress/partial/pending/prohibited`。

## Review focus

- 相同 Target + Snapshot 是否确定产生相同输出，且相同 trigger、新 trigger/相同 input、新 trigger/新 Snapshot 三条路径是否被正确区分。
- 是否保留足够审计信息解释 delta。
- 是否避免绕过 Risk。

## Risks and rollback

- TargetResolver 错误会造成过买/过卖；必须优先保证不下错单。
