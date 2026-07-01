---
id: TASK-007
title: Implement trade ledger and portfolio projection
status: blocked
depends_on: [TASK-004, TASK-006]
spec_refs: [INV-CONSISTENCY, CONTRACT-BROKER-TRADE-V1, STORAGE-SOT]
allowed_paths: [src/quantiqmt/account/**, src/quantiqmt/portfolio/**, tests/unit/ledger/**, tests/integration/portfolio/**]
forbidden_paths: [src/quantiqmt/strategy/**]
verification:
  commands: ["poetry run pytest tests/unit/ledger tests/integration/portfolio"]
---

# Objective

实现成交去重、双重记账、持仓投影和 Snapshot/Replay。

## Acceptance criteria

- [ ] 同一 Broker Trade 只记账一次。
- [ ] 每个 transaction 同币种借贷平衡。
- [ ] Snapshot 恢复与空库 Replay checksum 一致。
- [ ] Broker 差异不覆盖历史，产生 Reconciliation Case。
