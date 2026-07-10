---
id: TASK-007
title: Implement trade ledger and portfolio projection
status: blocked
depends_on: [TASK-004, TASK-006, TASK-018]
spec_refs: [INV-CONSISTENCY, CONTRACT-BROKER-TRADE-V1, CONTRACT-LEDGER-TRADE-POSTED-V1, CONTRACT-PORTFOLIO-POSITION-CHANGED-V1, STORAGE-SOT, REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths: [src/quantiqmt/account/**, src/quantiqmt/portfolio/**, tests/unit/ledger/**, tests/unit/portfolio/**, tests/integration/portfolio/**]
forbidden_paths: [src/quantiqmt/strategy/**]
verification:
  commands: ["poetry run pytest tests/unit/ledger tests/integration/portfolio"]
---

# Objective

实现成交去重、双重记账、持仓投影和 Snapshot/Replay。

## Blocking reason

需要 TASK-018 冻结 Ledger account model、entry taxonomy、费用/税费、成本法、position projection、portfolio snapshot、reconciliation repair command 和 checksum 语义。

## Non-goals

- 不直接消费 Broker 持仓覆盖内部历史。
- 不修改 OMS Order 状态。
- 不实现 Strategy attribution 的业务策略规则，除非 TASK-018 已定义。

## Acceptance criteria

- [ ] 同一 Broker Trade 只记账一次。
- [ ] 每个 transaction 同币种借贷平衡。
- [ ] Snapshot 恢复与空库 Replay checksum 一致。
- [ ] Broker 差异不覆盖历史，产生 Reconciliation Case。
- [ ] PositionChanged 由 Ledger transaction 幂等投影产生，不直接绕过 Ledger。
- [ ] Property tests 覆盖重复成交、乱序成交、费用税费、零持仓和 replay。

## Review focus

- Ledger append-only 与 debit/credit balance。
- 价格、金额、费用不得使用 float。
- Broker 差异必须走 Reconciliation/Adjustment，不得 SQL 覆盖。

## Risks and rollback

- Ledger 错误会污染 Portfolio 和 Risk；发现不平衡必须隔离并报警。
