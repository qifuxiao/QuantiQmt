---
id: TASK-008
title: Implement strategy SDK and isolated runtime contract
status: blocked
depends_on: [TASK-002]
spec_refs: [PORTS-STRATEGY, SM-STRATEGY, CONTRACT-STRATEGY-TARGET-V1]
allowed_paths: [src/quantiqmt/strategy_sdk/**, src/quantiqmt/strategy_runtime/**, tests/contract/strategy/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/order/infrastructure/**]
verification:
  commands: ["poetry run pytest tests/contract/strategy", "poetry run mypy src/quantiqmt/strategy_sdk src/quantiqmt/strategy_runtime"]
---

# Objective

实现 Strategy Protocol、只读 Context、Checkpoint 和 Runtime 状态/资源边界。

## Acceptance criteria

- [ ] SDK 不暴露 Broker、DB、Redis、OMS Repository。
- [ ] 只有 RUNNING generation 能输出。
- [ ] 回调串行、deadline 有界，异常使策略 PAUSED/ERROR。
- [ ] Checkpoint 校验版本/checksum，重复事件处理幂等。
