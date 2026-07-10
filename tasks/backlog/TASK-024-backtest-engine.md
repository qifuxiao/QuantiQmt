---
id: TASK-024
title: Implement deterministic backtest engine and simulation harness
status: blocked
depends_on: [TASK-006, TASK-008, TASK-009, TASK-021, TASK-023]
spec_refs: [PORTS-CORE, PORTS-STRATEGY, WF-SUBMIT-ORDER, NFR-PERFORMANCE, NFR-RELIABILITY]
allowed_paths: [src/quantiqmt/backtest/**, src/quantiqmt/simulation/**, tests/unit/backtest/**, tests/integration/backtest/**]
forbidden_paths: [src/quantiqmt/live/qmt/**]
verification:
  commands:
    - poetry run pytest tests/unit/backtest tests/integration/backtest
    - poetry run mypy src/quantiqmt/backtest src/quantiqmt/simulation
---

# Objective

实现 VirtualClock、HistoricalMarket、deterministic Scheduler、ExecutionSimulator、费用/滑点和 Backtest metrics。

## Non-goals

- 不实现真实 Broker。
- 不改变 Strategy SDK 或 OMS 语义。
- 不提供收益承诺。

## Acceptance criteria

- [ ] 相同输入、配置和 seed 产生相同 checksum。
- [ ] 无未来函数 contract tests 通过。
- [ ] Strategy logic 与 Live Runtime 共享同一 SDK 契约。
- [ ] 费用、滑点、成交延迟和 session 行为可配置且可审计。

## Review focus

- 是否只替换 Clock/Market/Execution/Scheduler。
- 是否能证明 deterministic。
- 是否与 live contracts 保持一致。

## Risks and rollback

- Backtest 是策略准入入口，必须避免乐观偏差。
