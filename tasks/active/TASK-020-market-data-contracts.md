---
id: TASK-020
title: Complete Market data and MarketGateway L4 contracts
status: active
depends_on: [TASK-046]
spec_refs: [PORTS-CORE, CONTRACT-CATALOG, NFR-PERFORMANCE, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/storage/**, spec/nfr/**, tests/contract/messages/**, tasks/active/TASK-020-market-data-contracts.md, tasks/active/README.md, tasks/backlog/TASK-023-market-gateway.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/unit/**, tests/property/**, tests/integration/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: draft
  implementation_status: in_progress
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

冻结 market.tick_received、market.bar_closed、market.quality_changed、market.session_changed、MarketGateway、BarAggregator 和 MarketQuality 契约。

## Non-goals

- 不接 MiniQMT。
- 不实现行情网关。
- 不定义具体策略逻辑。

## Acceptance criteria

- [ ] 激活并定义市场事件 JSON Schema、fixtures 和 catalog 路由。
- [ ] 定义 MarketGateway subscribe/unsubscribe/snapshot/health/backpressure 语义。
- [ ] 定义 session、trading calendar、gap/stale/quality state 和恢复行为。
- [ ] 定义 BarAggregator 输入、输出、watermark 和 replay determinism。
- [ ] 为后续 MarketGateway implementation task 提供 allowed_paths、verification 和 Review 重点。

## Activation evidence

- On 2026-08-11, a human explicitly authorized starting the next task after synchronizing with the latest `main`; the coordinator selected TASK-020 as the dependency-order-first ready candidate.
- TASK-046 is completed with trusted schema-v1 delivery, passed acceptance, formal independent APPROVE evidence, and a merge commit, satisfying TASK-020's sole dependency gate.
- This change only activates TASK-020 for Market data and MarketGateway L4 contract work. It is not implementation completion, Review approval, release authorization, or downstream dependency unlock evidence.
- TASK-022 remains backlog/ready and unactivated. TASK-021, TASK-023, and every other blocked task remain blocked.

## Review focus

- 行情质量问题是否显式传播给 Strategy/Risk。
- Backpressure 是否有界且不丢交易审计消息。
- Live 与 Backtest 是否共享事件语义。

## Risks and rollback

- 市场数据错误会诱发策略错误；必须明确 gap/stale 语义。
