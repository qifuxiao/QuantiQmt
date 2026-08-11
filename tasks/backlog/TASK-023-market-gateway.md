---
id: TASK-023
title: Implement MarketGateway and market quality pipeline
status: blocked
depends_on: [TASK-020, TASK-022]
spec_refs: [PORTS-MARKET, CONTRACT-MARKET-TICK-RECEIVED-V1, CONTRACT-MARKET-BAR-CLOSED-V1, CONTRACT-MARKET-QUALITY-CHANGED-V1, CONTRACT-MARKET-SESSION-CHANGED-V1, CONTRACT-MARKET-DATA-V1, WF-MARKET-DATA, STORAGE-SOT, STORAGE-MARKET-DATA, NFR-PERFORMANCE, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths: [src/quantiqmt/market/**, tests/unit/market/**, tests/contract/market/**, tests/integration/market/**]
forbidden_paths: [src/quantiqmt/live/qmt/**, src/quantiqmt/strategy/**, src/quantiqmt/order/**]
verification:
  commands:
    - poetry run pytest tests/unit/market tests/contract/market tests/integration/market
    - poetry run pytest tests/contract/messages/test_market_data_contracts.py
    - poetry run mypy src/quantiqmt/market
---

# Objective

实现 MarketGateway 抽象、行情标准化、BarAggregator、MarketQuality 和有界 backpressure，不接 MiniQMT。

## Non-goals

- 不实现具体 live-qmt adapter。
- 不实现 Strategy Runtime。
- 不把 Redis 作为行情权威来源。

## Acceptance criteria

- [ ] Tick/Bar/Quality/Session 契约测试通过。
- [ ] Subscribe/unsubscribe 幂等，callback 只做标准化和有界入队。
- [ ] Gap/stale/quality 状态可观测并传播。
- [ ] Replay 与 live 输入产生一致标准化事件。

## Frozen implementation deliverables

- Implement the exact `PORTS-MARKET` operations and `CONTRACT-MARKET-DATA-V1` DTOs; do not invent adapter-specific public DTOs, outcomes, or exceptions.
- Resolve and validate all four public market schemas plus mandatory semantic rules; preserve canonical Decimal strings and reject JSON floats for precise values.
- Keep callbacks limited to normalization and bounded enqueue, with deterministic gap/quality evidence for any permitted coalesce/drop and no effect on trading or audit queues.
- Inject clock, calendar, session, aggregation policy, and replay inputs; do not read wall clock, ambient randomness, future data, or silently revise final bars.
- Treat upstream market data and versioned calendars as authoritative; Redis/cache remains non-authoritative and any future database migration requires separate authorization.
- MiniQMT connectivity remains outside this task and belongs to the separately governed live adapter work.

## Review focus

- 背压是否有界。
- 是否不会阻塞 MiniQMT callback。
- 是否保留行情质量证据。

## Risks and rollback

- 行情延迟和质量错误必须 fail-visible，不得静默。
