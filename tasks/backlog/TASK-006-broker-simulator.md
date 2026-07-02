---
id: TASK-006
title: Implement execution port and programmable broker simulator
status: blocked
depends_on: [TASK-003, TASK-005]
spec_refs: [INV-TRADING, PORTS-CORE, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, NFR-RELIABILITY, CONTRACT-CANCEL-ORDER-V1, CONTRACT-EXECUTION-ATTEMPT-STARTED-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1, CONTRACT-BROKER-ORDER-REPORTED-V1]
allowed_paths: [src/quantiqmt/execution/**, src/quantiqmt/simulation/broker/**, tests/contract/broker/**]
forbidden_paths: [src/quantiqmt/live/qmt/**]
verification:
  commands: ["poetry run pytest tests/contract/broker"]
---

# Objective

实现 Execution Port 和可脚本控制的 Broker Simulator，暂不接 MiniQMT。

## Acceptance criteria

- [ ] 支持确认、拒单、部分成交、重复、乱序、延迟和断连。
- [ ] Submit/Cancel timeout 返回 UNKNOWN_OUTCOME。
- [ ] 过期 fencing token 被拒绝。
- [ ] 同 idempotency_key 不产生第二笔模拟外部订单。
