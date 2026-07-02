---
id: TASK-010
title: Implement reference buy-and-hold strategy
status: blocked
depends_on: [TASK-009]
spec_refs: [PORTS-STRATEGY, SM-STRATEGY, WF-SUBMIT-ORDER]
allowed_paths: [strategies/reference/buy_and_hold/**, tests/strategies/buy_and_hold/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/order/**, src/quantiqmt/risk/**]
verification:
  commands: ["poetry run pytest tests/strategies/buy_and_hold"]
---

# Objective

实现仅用于验证全链路的 Buy and Hold TargetPosition 参考策略。

## Acceptance criteria

- [ ] 重复行情不产生重复 Target。
- [ ] 只通过 Strategy SDK 和 TargetPosition 输出。
- [ ] Checkpoint 恢复与连续运行一致。
- [ ] 部分成交、活动订单和重启场景端到端通过。
- [ ] 文档明确不构成收益承诺或自动实盘批准。
