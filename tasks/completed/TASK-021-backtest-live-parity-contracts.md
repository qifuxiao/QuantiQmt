---
id: TASK-021
title: Complete Backtest and Live parity L4 contracts
status: completed
depends_on: [TASK-046, TASK-016, TASK-017, TASK-020]
spec_refs: [INV-TRADING, INV-CONSISTENCY, PORTS-CORE, PORTS-STRATEGY, PORTS-MARKET, PORTS-BROKER-SIMULATOR, CONTRACT-BACKTEST-PARITY-V1, CONTRACT-BACKTEST-PARITY-SEMANTIC-V1, PORTS-BACKTEST, WF-BACKTEST-RUN, NFR-PERFORMANCE, NFR-RELIABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/nfr/**, tests/contract/messages/**, tasks/backlog/TASK-010-reference-buy-hold.md, tasks/backlog/TASK-021-backtest-live-parity-contracts.md, tasks/active/TASK-021-backtest-live-parity-contracts.md, tasks/completed/TASK-021-backtest-live-parity-contracts.md, tasks/active/README.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/unit/**, tests/property/**, tests/integration/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_independent_review
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/82
    reviewed_head_sha: cf71ff8a8238c07977f33ff7643a5d62ed242ac4
    review_verdict: APPROVE
    reviewer: qfxyyy
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/82#pullrequestreview-5027595585
    merge_commit_sha: cd2e7a5e9528abe0e94d7f64dacbc30438873517
    ci_evidence: reviewed_head_final_4_of_4_success_quality_x2_persistence_postgresql_x2
    human_authorization_evidence: >-
      2026-08-26 user confirmed PR #82 merged and explicitly approved execution of the
      TASK-021 active-to-completed governance closeout. This authorization adds only the
      exact completed TASK-021 path, activates no downstream task, and does not authorize
      Backtest runtime, storage, migration, Live adapter, deployment, or release.
---

# Objective

冻结 Backtest/Live 统一架构：共享 Domain/Application/Strategy logic，仅替换 Clock、Market、Execution、Scheduler 和 storage adapters。

## Activation evidence

- 2026-08-26 人类明确批准激活并实施 TASK-021；该授权仅覆盖本任务 backlog→active、L4 规范/契约测试实现及 TASK-010 handoff 更新。
- 直接依赖 TASK-046、TASK-016、TASK-017、TASK-020 均为 completed，并分别具有通过的 acceptance、正式独立 Review 与可信 completion evidence。
- 本次授权不包含 Backtest runtime、数据库/migration、Live adapter、TASK-010/TASK-024 激活、部署、发布或 active→completed 收尾。

## Non-goals

- 不实现 Backtest engine。
- 不承诺收益或回测准确度。
- 不允许未来函数。

## Acceptance criteria

- [x] 定义 VirtualClock、deterministic Scheduler、HistoricalMarket 和 ExecutionSimulator Port。
- [x] 定义费用、滑点、撮合、成交回报、延迟和日历/session 语义。
- [x] 定义 no-lookahead 规则、data availability、checksum 和 reproducibility evidence。
- [x] 定义 Live/Backtest parity contract tests。
- [x] 更新 TASK-010，使参考策略只验证闭环，不隐式定义平台行为。

## Implementation evidence

- `CONTRACT-BACKTEST-PARITY-V1` 与 Semantic Contract 冻结严格内部 DTO、不可变 artifact 引用、RFC8785/SHA-256/UUIDv5 固定向量、I-JSON 安全整数、Decimal-only 金额及 completed/failed/rejected reproducibility evidence；既有公开消息契约未修改。
- `PORTS-BACKTEST` 与 `WF-BACKTEST-RUN` 冻结 VirtualClock、有界确定性 Scheduler、通过 `WAIT → HISTORICAL_RELEASE` 在不泄露未来 payload 的前提下按 recorded `available_at` 活跃推进的 HistoricalMarket、复用既有 ExecutionGateway/Broker report 的 ExecutionSimulator，以及隔离但保持共享 UoW/Journal/Inbox/Outbox/Snapshot 语义的 Storage boundary。
- 同一 Domain/Application/Strategy/TargetResolver/Risk/OMS/Ledger/Portfolio 逻辑用于 Live 与 Backtest；唯一订单链仍为 `OrderIntent → OMS 注册 → Risk → OMS 迁移 → Execution → Broker reports → OMS merge → Ledger/Portfolio`，禁止 simulator 直接改状态或回测专用策略分支。
- 撮合模型锁定 submit cutoff 与 accepted business time 双门禁、竞争订单全序和增量流动性只消费一次、DAY/IOC/FOK 与 scenario fill authority、逆向滑点、limit/price-band 独立校验、每订单累计差额最低佣金、逐笔 transfer fee/sell tax、确定性 latency 及 end-boundary fail-closed；UNKNOWN 保持同一身份并对账。
- 两级 parity 仅比较共享业务逻辑或已记录外部事实 replay；normalization 只排除 adapter telemetry，保留业务身份、因果、时间、结果、错误、版本与 checksum。`MATCH` 要求零 mismatch、零 future read，且永不代表生产放行。
- `tests/contract/messages/test_backtest_live_parity_contracts.py` 提供 schema/semantic、固定向量、未来数据拒绝、调度全序、撮合/流动性/费用、部分成交最低佣金、K 线追溯成交拒绝、parity normalization、NFR 与 TASK-010 handoff 的可执行正负证据。
- TASK-010 已增加本任务输出引用和冻结实现边界；它仍保持 blocked，且本任务未激活 TASK-010 或 TASK-024。

## Deferred production boundary

- 本任务不实现 Backtest engine、物理存储、migration、Live adapter、部署或发布。后续 runtime 必须由单独的人类授权任务实现并通过独立 Review；当前 release 保持 `prohibited`。

## Verification evidence

- `poetry run python scripts/validate_specs.py`：通过。
- `poetry run pytest tests/spec tests/contract -q`：`711 passed in 30.79s`。
- `poetry run pytest tests/contract/messages/test_backtest_live_parity_contracts.py -q`：`48 passed`。
- `poetry run ruff check` 与 `poetry run ruff format --check`：TASK-021 涉及的两个契约测试文件通过。
- 以上为实现阶段的本地证据；独立 Review、CI、merge 与 completed delivery 由下方精确 closeout evidence 补足，release 仍保持 `prohibited`。

## Review focus

- 是否同一策略逻辑可在 Backtest/Simulation/Live 使用。
- 是否能证明无未来函数。
- 是否保留足够审计与指标。

## Risks and rollback

- 错误 Backtest 会产生虚假信心；必须比普通功能更严格。

## Final review and closeout evidence

- PR #82 was formally approved by independent collaborator `qfxyyy` on exact reviewed Head `cf71ff8a8238c07977f33ff7643a5d62ed242ac4`: https://github.com/qifuxiao/QuantiQmt/pull/82#pullrequestreview-5027595585.
- GitHub reports 4/4 successful checks on the reviewed Head: quality jobs `98087450030` and `98087369216`, plus persistence-postgresql jobs `98087449843` and `98087368944`.
- PR #82 merged into `main` as `cd2e7a5e9528abe0e94d7f64dacbc30438873517`.
- Closeout verification passed against merged `main`: `poetry run python scripts/validate_specs.py` passed and `poetry run pytest tests/spec tests/contract -q` recorded `711 passed in 32.36s` through Poetry 2.1.4 with the repository's locked dependencies.
- The 2026-08-26 human closeout authorization is limited to this governance transition. TASK-010 remains blocked by TASK-008 and TASK-009; TASK-024 remains blocked by its runtime dependencies. Both require separate human activation, and runtime, physical storage, migration, deployment, and release remain prohibited.
