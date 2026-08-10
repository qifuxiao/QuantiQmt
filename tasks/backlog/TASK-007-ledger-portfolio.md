---
id: TASK-007
title: Implement trade ledger and portfolio projection
status: blocked
depends_on: [TASK-004, TASK-006, TASK-018]
spec_refs: [INV-CONSISTENCY, CONTRACT-BROKER-TRADE-V1, CONTRACT-LEDGER-TRADE-POSTED-V1, CONTRACT-PORTFOLIO-POSITION-CHANGED-V1, CONTRACT-LEDGER-ACCOUNTING-V1, CONTRACT-PORTFOLIO-PROJECTION-V1, CONTRACT-RECONCILIATION-V1, PORTS-LEDGER-PORTFOLIO, REPO-LEDGER-PORTFOLIO, STORAGE-SOT, STORAGE-LEDGER-PORTFOLIO, SM-PORTFOLIO, SM-RECONCILIATION-CASE, WF-TRADE-ACCOUNTING, WF-RECONCILIATION-REPAIR, REVIEW-IMPLEMENTATION-READINESS-0.7]
allowed_paths: [src/quantiqmt/account/**, src/quantiqmt/portfolio/**, tests/unit/ledger/**, tests/unit/portfolio/**, tests/integration/portfolio/**]
forbidden_paths: [src/quantiqmt/strategy/**]
verification:
  commands: ["poetry run pytest tests/unit/ledger tests/integration/portfolio"]
---

# Objective

实现成交去重、双重记账、持仓投影和 Snapshot/Replay。

## Blocking reason

TASK-018 已在 draft 契约中冻结 Ledger account model、entry taxonomy、费用/税费、成本法、position projection、portfolio snapshot、reconciliation repair command 和 checksum 语义；本任务仍保持 blocked，直到 TASK-004、TASK-006、TASK-018 均以可信 completion evidence 完成且由人类激活。

## Implementation constraints

- 只能实现 `SPEC-0.9.0` 登记的 Ledger/Portfolio/Reconciliation 契约；不得自行发明或改变账户分类、entry type、成本法、PnL、rounding、identity、Case/repair、状态迁移或失败码。
- V1 只实现 `WEIGHTED_AVERAGE_V1` 与 long-only `FLAT/LONG` Position。新成本法、short/小数持仓或 FX posting 需要独立 spec-change。
- 必须先执行 Schema 与语义校验，再进入 Repository；不平衡、账户缺失、scope/currency/instrument 不一致、重复 identity 冲突、版本/序列回退、坏 snapshot、过期 evidence/fencing 均 fail-closed。
- Ledger、projection journal、Case evidence/transition、repair/audit 全部 append-only。Broker snapshot 只能创建证据/Case，不能覆盖内部 Ledger/Portfolio 历史。
- Repair 只能追加 adjustment/compensating facts；UNKNOWN 使用同一 command/idempotency identity 查询和对账，禁止盲目重试。
- 本任务不得在未获得人类授权且 allowed paths 未覆盖时创建 migration 或部署持久化 schema；需要 PostgreSQL migration 时必须先走独立治理授权。

## Non-goals

When a human later activates this task, implementation must use the frozen semantics without invention: exact active account selection by canonical `(scope_id, account_id, currency, account_type, instrument_id)`, authoritative Broker Trade/NFC fingerprints including independently typed fee evidence and fixed entry slots, explicit T+1 settlement-release DTO/result with unchanged Ledger checkpoint and exact version increments, single-currency snapshots, Ledger-replayable projection-state checksum, and discriminated adjustment/compensating facts bound to Case/command/checksum without fake Trades. LedgerEntry remains embedded-only and the operation-specific Result/error matrices are authoritative. TASK-007 remains blocked and performs no work in TASK-018.

- 不直接消费 Broker 持仓覆盖内部历史。
- 不修改 OMS Order 状态。
- 不实现 Strategy attribution 的业务策略规则，除非 TASK-018 已定义。

## Acceptance criteria

- [ ] 同一 Broker Trade 只记账一次。
- [ ] 每个 transaction 同币种借贷平衡。
- [ ] Snapshot 恢复与空库 Replay checksum 一致。
- [ ] Broker 差异不覆盖历史，产生 Reconciliation Case。
- [ ] PositionChanged 由 Ledger transaction 幂等投影产生，不直接绕过 Ledger。
- [ ] Property tests 覆盖重复成交、乱序成交、费用税费、零持仓和 replay。

## Review focus

- Ledger append-only 与 debit/credit balance。
- 价格、金额、费用不得使用 float。
- Broker 差异必须走 Reconciliation/Adjustment，不得 SQL 覆盖。

## Risks and rollback

- Ledger 错误会污染 Portfolio 和 Risk；发现不平衡必须隔离并报警。
