---
id: TASK-006
title: Implement execution port and programmable broker simulator
status: blocked
depends_on: [TASK-004, TASK-005, TASK-017]
spec_refs: [INV-TRADING, PORTS-CORE, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, NFR-RELIABILITY, CONTRACT-CANCEL-ORDER-V1, CONTRACT-EXECUTION-ATTEMPT-STARTED-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths: [src/quantiqmt/execution/**, src/quantiqmt/simulation/broker/**, tests/contract/broker/**]
forbidden_paths: [src/quantiqmt/live/qmt/**]
verification:
  commands: ["poetry run pytest tests/contract/broker"]
---

# Objective

实现 Execution Port 和可脚本控制的 Broker Simulator，暂不接 MiniQMT。

## Blocking reason

需要 TASK-017 冻结 Execution/Broker DTO、capabilities、fencing、timeout/UNKNOWN、simulator scenario DSL、fill model 和 contract fixtures。还需要 TASK-004 提供持久化/outbox，TASK-005 提供 Risk approve/reject 语义。

## Non-goals

- 不接入 MiniQMT 或真实 Broker。
- 不解释订单业务状态；OMS 仍是唯一状态 owner。
- 不实现 Ledger 或 Portfolio。

## Acceptance criteria

- [ ] 支持确认、拒单、部分成交、重复、乱序、延迟和断连。
- [ ] Submit/Cancel timeout 返回 UNKNOWN_OUTCOME。
- [ ] 过期 fencing token 被拒绝。
- [ ] 同 idempotency_key 不产生第二笔模拟外部订单。
- [ ] Scenario DSL deterministic；相同 seed、输入和 clock 得到相同 Broker reports/trades。
- [ ] Contract tests 覆盖 duplicate, out-of-order, timeout, disconnect, stale fencing 和 cancel-race。

## Review focus

- UNKNOWN 是否只触发对账，不盲目重提/重撤。
- idempotency_key 是否稳定且与 client_order_id 关联。
- Broker simulator 是否不会推进 OMS 状态。

## Risks and rollback

- Simulator 语义会成为后续 Backtest/Live 契约基准；不得为了测试方便弱化真实异常。
