---
id: TASK-027
title: Implement reconciliation engine and repair workflows
status: blocked
depends_on: [TASK-004, TASK-006, TASK-007, TASK-018, TASK-022]
spec_refs: [INV-CONSISTENCY, SM-RECONCILIATION-CASE, WF-RECOVERY, WF-BROKER-RECONNECT, STORAGE-SOT, NFR-OBSERVABILITY]
allowed_paths: [src/quantiqmt/reconciliation/**, tests/unit/reconciliation/**, tests/integration/reconciliation/**]
forbidden_paths: [src/quantiqmt/order/domain/**, src/quantiqmt/strategy/**]
verification:
  commands:
    - poetry run pytest tests/unit/reconciliation tests/integration/reconciliation
    - poetry run mypy src/quantiqmt/reconciliation
---

# Objective

实现 Broker/内部订单/成交/账本/持仓差异分类、Case 生命周期、修复命令、审批和审计。

## Non-goals

- 不直接 SQL 覆盖历史事实。
- 不修改 Order Domain 状态机。
- 不实现人工 UI。

## Acceptance criteria

- [ ] 差异分类可重复、可审计，P0/P1 不可自动关闭。
- [ ] 修复命令只追加事实或调整分录。
- [ ] Recovery barrier 依赖未解决差异状态。
- [ ] 重复 broker facts 和 late facts 幂等。

## Review focus

- 是否遵守 Source of Truth。
- 是否所有修复都有审批、证据和前后版本。
- 是否禁止覆盖/删除历史。

## Risks and rollback

- 错误修复比原始差异更危险；必须默认人工审批和可回滚调整事实。
