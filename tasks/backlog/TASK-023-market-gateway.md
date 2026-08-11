---
id: TASK-023
title: Implement MarketGateway and market quality pipeline
status: blocked
depends_on: [TASK-020, TASK-022]
spec_refs: [PORTS-MARKET, CONTRACT-MARKET-TICK-RECEIVED-V1, CONTRACT-MARKET-BAR-CLOSED-V1, CONTRACT-MARKET-QUALITY-CHANGED-V1, CONTRACT-MARKET-SESSION-CHANGED-V1, CONTRACT-MARKET-DATA-V1, CONTRACT-MARKET-SEMANTIC-VALIDATION-V1, WF-MARKET-DATA, STORAGE-SOT, STORAGE-MARKET-DATA, NFR-PERFORMANCE, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths: [src/quantiqmt/market/**, src/quantiqmt/contracts/**, tests/unit/market/**, tests/unit/contracts/**, tests/contract/market/**, tests/contract/contracts/**, tests/integration/market/**, pyproject.toml]
forbidden_paths: [src/quantiqmt/live/qmt/**, src/quantiqmt/strategy/**, src/quantiqmt/order/**]
verification:
  commands:
    - poetry run pytest tests/unit/market tests/contract/market tests/integration/market
    - poetry run pytest tests/contract/messages/test_market_data_contracts.py
    - poetry run pytest tests/unit/contracts tests/contract/contracts -k "schema_bundle or registry"
    - poetry build
    - poetry run pytest tests/contract/contracts/test_installed_schema_bundle.py
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
- Keep callbacks limited to normalization and bounded enqueue. V1 forbids Tick coalescing: overflow rejects the new item and emits deterministic lost-sequence gap/quality evidence without affecting trading or audit queues.
- Inject clock, calendar, session, aggregation policy, and replay inputs; do not read wall clock, ambient randomness, future data, or silently revise final bars.
- Treat upstream market data and versioned calendars as authoritative; Redis/cache remains non-authoritative and any future database migration requires separate authorization.
- MiniQMT connectivity remains outside this task and belongs to the separately governed live adapter work.
- Build one immutable `quantiqmt.contracts.schema_bundle` package resource generated from the reviewed `spec/manifest.yaml` contract index. The bundle records manifest version, every canonical contract ID/path/digest and an overall bundle digest; generation fails on duplicates, missing routes, unresolved refs or parity mismatch.
- Runtime Registry loads only that installed package resource, verifies manifest-version parity and bundle/content digests before serving a schema, and fails closed for missing, tampered, partial or mismatched bundles. Runtime must never read a source-checkout `spec/contracts/**` path and must not maintain a second hand-copied schema set.
- Wheel/build verification installs the artifact in an isolated environment without the source checkout, validates every active Market route and semantic-contract digest, and proves missing/tampered bundle failure. `pyproject.toml` may change only as required to package the reviewed generated resource.

## Review focus

- 背压是否有界。
- 是否不会阻塞 MiniQMT callback。
- 是否保留行情质量证据。

## Risks and rollback

- 行情延迟和质量错误必须 fail-visible，不得静默。
