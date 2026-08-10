---
id: TASK-018
title: Complete Ledger, Portfolio, and Reconciliation L4 contracts
status: active
depends_on: [TASK-046]
spec_refs: [INV-CONSISTENCY, STORAGE-SOT, STORAGE-LEDGER-PORTFOLIO, SM-ACCOUNT, SM-PORTFOLIO, SM-RECONCILIATION-CASE, CONTRACT-BROKER-TRADE-V1, CONTRACT-LEDGER-TRADE-POSTED-V1, CONTRACT-PORTFOLIO-POSITION-CHANGED-V1, CONTRACT-LEDGER-ACCOUNTING-V1, CONTRACT-PORTFOLIO-PROJECTION-V1, CONTRACT-RECONCILIATION-V1, PORTS-LEDGER-PORTFOLIO, REPO-LEDGER-PORTFOLIO, WF-TRADE-ACCOUNTING, WF-RECONCILIATION-REPAIR]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/state-machines/**, spec/workflows/**, spec/repositories/**, spec/storage/**, tests/contract/messages/**, tasks/backlog/TASK-007-ledger-portfolio.md, tasks/active/TASK-018-ledger-portfolio-contracts.md, tasks/index.yaml]
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

冻结双重记账、成交入账、持仓投影、Portfolio snapshot/replay、成本/PnL、Reconciliation Case 和修复命令契约，使 TASK-007 可安全实现。

## Non-goals

- 不实现 Ledger/Portfolio 代码。
- 不直接修改 OMS Order 历史。
- 不用 Broker 持仓覆盖内部历史。

## Acceptance criteria

- [x] 定义 Ledger account model、entry types、debit/credit balance、currency、fee/tax 和 rounding。
- [x] 定义 Trade accounting workflow、幂等键、transaction_id 和 duplicate handling。
- [x] 定义 Position projection、cost basis、realized/unrealized PnL 和 position_version。
- [x] 定义 Snapshot/replay checksum 和 invalid snapshot fallback。
- [x] 定义 Reconciliation Case payload、repair commands、审批和审计。
- [x] 更新 TASK-007，使其可以直接实现。

## Acceptance evidence

- `CONTRACT-LEDGER-ACCOUNTING-V1` 与 `PORTS-LEDGER-PORTFOLIO` 冻结账户分类、正常余额、Decimal/rounding、交易/分录 identity、BUY/SELL/费用/税费和平衡失败。
- `WF-TRADE-ACCOUNTING`、`REPO-LEDGER-PORTFOLIO` 与 `STORAGE-LEDGER-PORTFOLIO` 冻结去重、乱序、append-only、CAS、原子提交、部分失败与 UNKNOWN 查询语义。
- `CONTRACT-PORTFOLIO-PROJECTION-V1` 冻结 `WEIGHTED_AVERAGE_V1`、long-only Position、版本/sequence、cost basis、realized/unrealized PnL 与 stale/missing market data。
- Portfolio Schema、`SM-PORTFOLIO` 和 `WF-RECOVERY` 冻结 canonical SHA-256 snapshot、严格 replay、坏快照完整 Ledger fallback 与 mismatch fail-closed。
- `CONTRACT-RECONCILIATION-V1`、`SM-RECONCILIATION-CASE` 与 `WF-RECONCILIATION-REPAIR` 冻结 evidence/owner/deadline/approval/audit、fencing、append-only repair 和 UNKNOWN。
- `tests/contract/messages/test_ledger_portfolio_contracts.py` 及三组 internal fixtures 机器验证正例覆盖和最低负例矩阵；TASK-007 保持 blocked 且引用全部冻结契约。

## Round-two acceptance evidence

- Account taxonomy and deterministic resolution are executable in JSON Schema and semantic fixtures, including inactive, duplicate, classification/type and instrument mismatch rejection.
- Broker Trade source fingerprint, repair fingerprint, UTF-8/NFC canonical JSON, fixed reference vectors, fee policy and fixed entry ordinals are executable contract tests.
- Explicit settlement-release request/result/Port semantics cover IMMEDIATE/T+1, verified calendar/checkpoint, CAS/fencing, duplicate, out-of-order, excess release and exact Position/Portfolio version increments.
- V1 snapshot is single-currency; projection-state checksum excludes random/valuation envelope, is reconstructed from Ledger facts, and replay/invalid-snapshot fallback is machine verified.
- Repair facts discriminate quantity, monetary and compensating facts from Trade, remain append-only/atomic, and bind approval/evidence/fencing and original UNKNOWN identity.
- Each operation has a schema-exhaustive outcome/code/reconciliation matrix; `QQ-STORAGE-7006` retains its existing meaning and deterministic collision uses additive `QQ-STORAGE-7011`.
- Fixture version chain is `3 -> 4 -> 5`; semantic/schema negative matrices reject every Review-requested prohibited state.

## Review remediation evidence for head after 51011b395ea2950be21b2678ee6372b41492b0a6

- `LedgerTransaction.transaction_kind` now provides schema-exclusive `TRADE`, `ADJUSTMENT`, and `COMPENSATING_FACT` routes. Repair facts bind canonical account, Case/version, repair command/fingerprint, action/fact/evidence, source checkpoint, authorization/fencing, and a verified repair-fact checksum; fixtures reject missing bindings, fabricated Trades, repair fields on Trades, and checksum mismatch.
- Canonical `account_id` is used by source Trade, accounting request, account selections, Ledger accounts, transactions, repository uniqueness, storage and workflow. Contract fixtures independently reject request, selection, account and transaction mismatches and duplicate identities.
- Source Trade now requires an independently typed fee amount/currency/rounding tuple. Fee is included in the source/request fingerprints and independently posted under `BROKER_CHARGES_V1`; fixtures reject missing/float/wrong-currency/wrong-rounding/policy-mismatched fees.
- `LedgerEntry` is frozen as an embedded-only `LedgerTransaction.entries` structure and is not independently routed by the top-level Schema or Port DTO list.
- TASK-018 remains active with draft/in-progress/pending/prohibited delivery; these fixes are awaiting independent Review and contain no runtime or migration implementation.
- Review P1 after head `32acd040cb97d62d9a29996cd04a6a983b88dc8c` is covered by a TRADE-only resolved Order UUID gate: public Broker v1 remains nullable/optional, while internal request/transaction Schema and semantic validation reject missing, null, non-canonical, invalid, or unresolved Order identity. `WF-TRADE-ACCOUNTING` machine-freezes reconciliation-only output and forbids Ledger/Portfolio output for unresolved trades; repair routes remain independent of Broker Order identity.
- Review P2 after head `9889d8afbda743ac729d4e26224f3eadc67d0bed` adds a complete sequence-4 `COMPENSATING_FACT` fixture with canonical identity/checksum chain and balanced entries. Direct Schema/semantic tests cover the valid route plus source-Trade injection, fact/kind mismatch, missing/null compensation identity, checksum mismatch and unbalanced entries; no frozen contract semantics changed.

## Review focus

- Ledger append-only 是否不可覆盖。
- Portfolio 是否仅由 Ledger/Trade facts 投影。
- Reconciliation 是否只追加调整事实，不删除历史。

## Risks and rollback

- Ledger 错误影响资金和风控；必须保守、可审计、可 replay。
- 本任务不创建 runtime、Repository 或 migration；发布保持 prohibited。未来持久化实现需要人类授权的 expand-only migration 范围。
- 独立 Review 前 `contract_status=draft`、`implementation_status=in_progress`、`review_status=pending`；回滚不得删除任何已采用的 Ledger、projection、Case、repair 或 audit 历史。
