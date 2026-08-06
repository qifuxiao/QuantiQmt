---
id: TASK-019
title: Complete Target Resolver L4 contracts
status: blocked
depends_on: [TASK-046, TASK-016, TASK-018]
spec_refs: [INV-TRADING, INV-RISK, PORTS-STRATEGY, CONTRACT-STRATEGY-TARGET-V1, CONTRACT-ORDER-INTENT-V1]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/storage/**, tests/contract/messages/**, tasks/backlog/TASK-009-target-resolver.md, tasks/backlog/TASK-019-target-resolver-contracts.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/unit/**, tests/property/**, tests/integration/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

冻结 TargetWeight/TargetPosition 到 OrderIntent 的确定性转换契约，包括 InstrumentSpec、price reference、rounding、active order effect、mandate/scope 和 idempotency。

## Non-goals

- 不实现 TargetResolver。
- 不执行 Risk approve。
- 不访问 Broker 或 OMS Repository。

## Acceptance criteria

- [ ] 定义 Target DTO、scope、strategy mandate、valid_until 和 replay semantics。
- [ ] 定义 InstrumentSpec、lot/tick、min quantity、price band、cash buffer 和 deadband。
- [ ] 定义 current position、strategy sleeve、portfolio snapshot 和 active order expected effect。
- [ ] 定义 deterministic resolution id、intent_id/idempotency key 和 NoAction/Rejected reasons。
- [ ] 更新 TASK-009，使其可直接实现。

## Review focus

- 相同 target 与 snapshot 是否确定产生相同输出。
- 是否保留足够审计信息解释 delta。
- 是否避免绕过 Risk。

## Risks and rollback

- TargetResolver 错误会造成过买/过卖；必须优先保证不下错单。
