---
id: TASK-010
title: Implement reference buy-and-hold strategy
status: blocked
depends_on: [TASK-008, TASK-009, TASK-021]
spec_refs: [PORTS-STRATEGY, SM-STRATEGY, WF-SUBMIT-ORDER, REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths: [strategies/reference/buy_and_hold/**, tests/strategies/buy_and_hold/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/order/**, src/quantiqmt/risk/**]
verification:
  commands: ["poetry run pytest tests/strategies/buy_and_hold"]
---

# Objective

实现仅用于验证全链路的 Buy and Hold TargetPosition 参考策略。

## Blocking reason

参考策略必须等待 Strategy SDK、TargetResolver 和 Backtest/Live parity 契约完成，避免把样例策略写成隐式平台规范。

## Non-goals

- 不承诺收益，不作为自动实盘批准。
- 不绕过 Strategy SDK、TargetResolver、OMS 或 Risk。
- 不把 e2e 缺口塞回策略代码。

## Acceptance criteria

- [ ] 重复行情不产生重复 Target。
- [ ] 只通过 Strategy SDK 和 TargetPosition 输出。
- [ ] Checkpoint 恢复与连续运行一致。
- [ ] 部分成交、活动订单和重启场景端到端通过。
- [ ] 文档明确不构成收益承诺或自动实盘批准。
- [ ] Backtest、simulation 和 limited-live dry-run 使用同一策略逻辑，只替换 clock/market/execution adapters。

## Review focus

- 参考策略是否仍然只是验证闭环，不引入平台特权。
- 是否存在未来函数、直接 Broker 访问或收益宣传。

## Risks and rollback

- 样例策略会被团队复制；必须极其保守、可解释、可审计。
