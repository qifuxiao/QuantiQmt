---
id: TASK-021
title: Complete Backtest and Live parity L4 contracts
status: blocked
depends_on: [TASK-046, TASK-016, TASK-017, TASK-020]
spec_refs: [INV-TRADING, INV-CONSISTENCY, PORTS-CORE, PORTS-STRATEGY, NFR-PERFORMANCE, NFR-RELIABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/nfr/**, tests/contract/messages/**, tasks/backlog/TASK-010-reference-buy-hold.md, tasks/backlog/TASK-021-backtest-live-parity-contracts.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/unit/**, tests/property/**, tests/integration/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

冻结 Backtest/Live 统一架构：共享 Domain/Application/Strategy logic，仅替换 Clock、Market、Execution、Scheduler 和 storage adapters。

## Non-goals

- 不实现 Backtest engine。
- 不承诺收益或回测准确度。
- 不允许未来函数。

## Acceptance criteria

- [ ] 定义 VirtualClock、deterministic Scheduler、HistoricalMarket 和 ExecutionSimulator Port。
- [ ] 定义费用、滑点、撮合、成交回报、延迟和日历/session 语义。
- [ ] 定义 no-lookahead 规则、data availability、checksum 和 reproducibility evidence。
- [ ] 定义 Live/Backtest parity contract tests。
- [ ] 更新 TASK-010，使参考策略只验证闭环，不隐式定义平台行为。

## Review focus

- 是否同一策略逻辑可在 Backtest/Simulation/Live 使用。
- 是否能证明无未来函数。
- 是否保留足够审计与指标。

## Risks and rollback

- 错误 Backtest 会产生虚假信心；必须比普通功能更严格。
