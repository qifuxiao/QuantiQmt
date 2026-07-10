---
id: TASK-026
title: Implement MiniQMT live adapters
status: blocked
depends_on: [TASK-006, TASK-023, TASK-025]
spec_refs: [INV-TRADING, PORTS-CORE, WF-BROKER-RECONNECT, WF-RECOVERY, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths: [src/quantiqmt/live/qmt/**, tests/contract/live_qmt/**, tests/integration/live_qmt/**]
forbidden_paths: [src/quantiqmt/order/domain/**, src/quantiqmt/strategy/**]
verification:
  commands:
    - poetry run pytest tests/contract/live_qmt
    - poetry run mypy src/quantiqmt/live/qmt
---

# Objective

实现 MiniQMT/xtquant 的 MarketGateway 和 BrokerGateway adapters，并证明断线、重连、心跳、查询和 UNKNOWN/reconciliation 语义。

## Non-goals

- 不修改核心 Domain。
- 不要求核心 CI 安装 QMT。
- 不绕过 Execution/OMS/Risk。

## Acceptance criteria

- [ ] Adapter 只位于 optional live-qmt 边界。
- [ ] QMT callback 有界入队，不阻塞核心链路。
- [ ] Submit/Cancel timeout 进入 UNKNOWN，对账后恢复。
- [ ] Reconnect 后先 SYNCING/Reconciliation，不能自动恢复 NORMAL。

## Review focus

- QMT 特有行为是否被隔离在 adapter。
- Fencing token 是否被执行。
- Live adapter 是否不能直接改订单状态。

## Risks and rollback

- 真实 Broker adapter 风险最高；必须先通过 Simulator/Paper/Limited Live。
