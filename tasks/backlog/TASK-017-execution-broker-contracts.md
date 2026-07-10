---
id: TASK-017
title: Complete Execution and Broker simulator L4 contracts
status: ready
depends_on: [TASK-014]
spec_refs: [INV-TRADING, PORTS-CORE, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, CONTRACT-EXECUTION-ATTEMPT-STARTED-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, CONTRACT-BROKER-TRADE-V1, NFR-RELIABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/nfr/**, tasks/backlog/TASK-006-broker-simulator.md, tasks/backlog/TASK-017-execution-broker-contracts.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

冻结 ExecutionGateway、BrokerGateway、Broker capabilities、fencing、UNKNOWN、simulator scenario DSL 和 fill/report 语义，使 TASK-006 可实现为后续 Live/Backtest 的共同基准。

## Non-goals

- 不接 MiniQMT。
- 不实现 Execution 或 Simulator 代码。
- 不改变 OMS 状态机。

## Acceptance criteria

- [ ] 定义 submit/cancel/query/open_orders/trades/account/positions 的 DTO、deadline、fencing 和 canonical outcomes。
- [ ] 定义 Broker capabilities、client_order_id 约束、rate limit 和 idempotency 语义。
- [ ] 定义 simulator scenario DSL：accept、reject、partial fill、full fill、duplicate、out-of-order、delay、disconnect、cancel race。
- [ ] 定义 simulator deterministic clock/seed 与 contract fixtures。
- [ ] 更新 TASK-006，使其不再需要自行发明 Broker/Execution 契约。

## Review focus

- UNKNOWN 是否禁止盲目重试。
- Simulator 是否模拟真实异常而非只模拟 happy path。
- Execution 是否不能推进订单业务状态。

## Risks and rollback

- 错误模拟器会让后续 Backtest/Live 误信错误语义。
