---
id: TASK-002
title: Implement versioned message contracts
status: ready
depends_on: [TASK-001, TASK-011]
spec_refs: [CONTRACT-MESSAGE-ENVELOPE-V1, CONTRACT-ORDER-INTENT-V1, CONTRACT-STRATEGY-TARGET-V1, CONTRACT-BROKER-TRADE-V1, CONTRACT-ORDER-STATUS-V1, CONTRACT-CANCEL-ORDER-V1, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-EXECUTION-ATTEMPT-STARTED-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, CONTRACT-LEDGER-TRADE-POSTED-V1, CONTRACT-PORTFOLIO-POSITION-CHANGED-V1]
allowed_paths: [src/quantiqmt/contracts/**, tests/contract/messages/**]
forbidden_paths: [src/quantiqmt/oms/**, src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/contract/messages", "poetry run mypy src/quantiqmt/contracts"]
---

# Objective

依据 JSON Schema 实现不可变 DTO、编码/解码和 golden fixtures。

## Acceptance criteria

- [ ] 所有必填、枚举、Decimal string、UTC 和 additionalProperties 规则一致。
- [ ] valid/minimal/maximal/invalid/unknown-enum fixtures 通过。
- [ ] 编码往返不损失精度，未知 schema version 明确失败。
- [ ] 未修改 spec Schema 以迁就实现。
