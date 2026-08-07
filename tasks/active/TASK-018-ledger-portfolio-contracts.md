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

## Review focus

- Ledger append-only 是否不可覆盖。
- Portfolio 是否仅由 Ledger/Trade facts 投影。
- Reconciliation 是否只追加调整事实，不删除历史。

## Risks and rollback

- Ledger 错误影响资金和风控；必须保守、可审计、可 replay。
- 本任务不创建 runtime、Repository 或 migration；发布保持 prohibited。未来持久化实现需要人类授权的 expand-only migration 范围。
- 独立 Review 前 `contract_status=draft`、`implementation_status=in_progress`、`review_status=pending`；回滚不得删除任何已采用的 Ledger、projection、Case、repair 或 audit 历史。
