---
id: TASK-010
title: Implement reference buy-and-hold strategy
status: blocked
depends_on: [TASK-008, TASK-009, TASK-021]
spec_refs: [PORTS-STRATEGY, PORTS-BACKTEST, SM-STRATEGY, WF-SUBMIT-ORDER, WF-BACKTEST-RUN, CONTRACT-BACKTEST-PARITY-V1, CONTRACT-BACKTEST-PARITY-SEMANTIC-V1, REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths: [strategies/reference/buy_and_hold/**, tests/strategies/buy_and_hold/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/order/**, src/quantiqmt/risk/**]
verification:
  commands: ["poetry run pytest tests/strategies/buy_and_hold"]
---

# Objective

实现仅用于验证全链路的 Buy and Hold TargetPosition 参考策略。

## Blocking reason

参考策略必须等待 Strategy SDK、TargetResolver 和 TASK-021 Backtest/Live parity 契约分别完成可信收尾；当前仍保持 blocked，且必须由人类另行激活。样例只能消费冻结 Port，不能成为隐式平台规范。

## Frozen implementation boundary

- Backtest、simulation 和 limited-live dry-run 必须加载同一 Strategy artifact、参数和 Checkpoint 逻辑；只替换 `PORTS-BACKTEST` 允许的 Clock、Market、Execution、Scheduler 与 storage adapter。
- 参考策略不得自行定义 VirtualClock、事件优先级、Historical availability、撮合、滑点、费用、延迟、日历/session、parity normalization 或 reproducibility identity；这些行为只来自 `CONTRACT-BACKTEST-PARITY-V1`、Semantic Contract 与 `WF-BACKTEST-RUN`。
- Buy-and-Hold 只通过 Strategy SDK 输出 TargetPosition；Target 必须进入 TargetResolver，生成的 Intent 仍经过 OMS 注册、Risk、OMS 迁移与 Execution。任何 Backtest-only 下单、直接状态赋值或 Broker shortcut 均为阻断问题。
- 验收仅证明参考闭环和已声明 parity case，不构成收益承诺、生产批准、Live 等价结果或自动发布证据。

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
