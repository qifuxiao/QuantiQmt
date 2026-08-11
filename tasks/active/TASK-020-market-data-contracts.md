---
id: TASK-020
title: Complete Market data and MarketGateway L4 contracts
status: active
depends_on: [TASK-046]
spec_refs: [PORTS-CORE, PORTS-MARKET, CONTRACT-CATALOG, CONTRACT-MESSAGE-ENVELOPE-V1, CONTRACT-MARKET-TICK-RECEIVED-V1, CONTRACT-MARKET-BAR-CLOSED-V1, CONTRACT-MARKET-QUALITY-CHANGED-V1, CONTRACT-MARKET-SESSION-CHANGED-V1, CONTRACT-MARKET-DATA-V1, CONTRACT-MARKET-SEMANTIC-VALIDATION-V1, WF-MARKET-DATA, STORAGE-SOT, STORAGE-MARKET-DATA, NFR-PERFORMANCE, NFR-RELIABILITY, NFR-OBSERVABILITY]
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
  acceptance_status: passed
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

- [x] 激活并定义市场事件 JSON Schema、fixtures 和 catalog 路由。
- [x] 定义 MarketGateway subscribe/unsubscribe/snapshot/health/backpressure 语义。
- [x] 定义 session、trading calendar、gap/stale/quality state 和恢复行为。
- [x] 定义 BarAggregator 输入、输出、watermark 和 replay determinism。
- [x] 为后续 MarketGateway implementation task 提供 allowed_paths、verification 和 Review 重点。

## Activation evidence

- On 2026-08-11, a human explicitly authorized starting the next task after synchronizing with the latest `main`; the coordinator selected TASK-020 as the dependency-order-first ready candidate.
- TASK-046 is completed with trusted schema-v1 delivery, passed acceptance, formal independent APPROVE evidence, and a merge commit, satisfying TASK-020's sole dependency gate.
- This change only activates TASK-020 for Market data and MarketGateway L4 contract work. It is not implementation completion, Review approval, release authorization, or downstream dependency unlock evidence.
- TASK-022 remains backlog/ready and unactivated. TASK-021, TASK-023, and every other blocked task remain blocked.

## Acceptance evidence

- Four Draft 2020-12 event schemas, minimal/maximal fixtures, targeted invalid fixtures, catalog routes, and manifest contract IDs freeze Tick, Bar, Quality, and Session payloads using canonical Decimal strings and UTC/version identities.
- `PORTS-MARKET` and `CONTRACT-MARKET-DATA-V1` freeze idempotent subscription fencing, absolute deadlines, bounded callback queues, exhaustive operation/health outcomes, snapshot evidence, and fail-visible backpressure.
- The public event schemas and internal semantic-validation rules make quality/reason, gap/watermark, calendar/session, monotonic version, and recovery-evidence contradictions machine-rejectable.
- `WF-MARKET-DATA` freezes ingress, normalization, quality publication, reconnect/backfill, and deterministic BarAggregator ordering, finality, late-data, and replay rules without ambient time or randomness.
- `STORAGE-MARKET-DATA`, `STORAGE-SOT`, and the NFR updates freeze upstream authority, non-authoritative cache behavior, optional tick durability, replay/checksum evidence, 50k msg/s assumptions, bounded thresholds, metrics, and low-cardinality alerts; no runtime or migration is authorized.
- TASK-023 remains blocked on TASK-020 and TASK-022, but now references the frozen contracts and has executable implementation deliverables and contract verification.
- Contract/schema/semantic fixtures are verified by `tests/contract/messages/test_market_data_contracts.py`; formal independent Review remains pending and release remains prohibited.
- Review corrections for rejected Head `8e50df8b215141dc87a6c25da03d5c1e73cbc757` add fail-closed Snapshot/Health thresholds, complete envelope binding and identity-collision fencing, RFC 8785 checksum/UUIDv5 reference vectors, executable Quality/Calendar/Session recovery rules, V1 no-coalesce backpressure, and a deployable immutable schema-bundle boundary for TASK-023. These are pre-release corrections to the same unpublished Market V1 contracts; they do not authorize runtime or release.
- Second-round corrections for rejected Head `7278f9e272f73ee61d1c7d6675f26dd6e78128a1` add an immutable checksum-bound Market validation policy; request/result/context validation for every Snapshot outcome and Health; deterministic freshness and status recomputation; I-JSON safe-integer and independent RFC 8785 vectors; and IANA tzdb/fold/UTC-offset replay evidence. TASK-020 remains active/draft/in-progress/pending/prohibited and no runtime or release is authorized.
- Final corrections for rejected Head `285f720f491dc2948b9cce11b46011eb99c37a99` make the IANA 2026c reference loader bundle-only: manifest version, exact zone list, manifest checksum, and every TZif SHA-256 are verified before `ZoneInfo.from_file`; no system-tzdb fallback or unbound cache is permitted. Observability regression coverage restores Risk timing cardinality/order under `risk_internal_joined_rule_audit_view` and excludes those fields from Market policy. Targeted contracts pass 359 tests and the full spec/contract suite passes 505 tests; TASK-020 remains active/draft/in-progress/pending/prohibited and no runtime or release is authorized.

## Review focus

- 行情质量问题是否显式传播给 Strategy/Risk。
- Backpressure 是否有界且不丢交易审计消息。
- Live 与 Backtest 是否共享事件语义。

## Risks and rollback

- 市场数据错误会诱发策略错误；必须明确 gap/stale 语义。
