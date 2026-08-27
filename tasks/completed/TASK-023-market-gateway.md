---
id: TASK-023
title: Implement MarketGateway and market quality pipeline
status: completed
depends_on: [TASK-020, TASK-022]
spec_refs: [PORTS-MARKET, CONTRACT-MARKET-TICK-RECEIVED-V1, CONTRACT-MARKET-BAR-CLOSED-V1, CONTRACT-MARKET-QUALITY-CHANGED-V1, CONTRACT-MARKET-SESSION-CHANGED-V1, CONTRACT-MARKET-DATA-V1, CONTRACT-MARKET-SEMANTIC-VALIDATION-V1, WF-MARKET-DATA, STORAGE-SOT, STORAGE-MARKET-DATA, NFR-PERFORMANCE, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths: [src/quantiqmt/market/**, src/quantiqmt/contracts/**, tests/unit/market/**, tests/unit/contracts/**, tests/contract/market/**, tests/contract/contracts/**, tests/integration/market/**, pyproject.toml, tasks/backlog/TASK-023-market-gateway.md, tasks/completed/TASK-023-market-gateway.md, tasks/active/README.md, tasks/index.yaml]
forbidden_paths: [src/quantiqmt/live/qmt/**, src/quantiqmt/strategy/**, src/quantiqmt/order/**]
verification:
  commands:
    - poetry run pytest tests/unit/market tests/contract/market tests/integration/market
    - poetry run pytest tests/contract/messages/test_market_data_contracts.py
    - poetry run pytest tests/unit/contracts tests/contract/contracts -k "schema_bundle or registry"
    - poetry build
    - poetry run pytest tests/contract/contracts/test_installed_schema_bundle.py
    - poetry run mypy src/quantiqmt/market
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_independent_review
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/84
    reviewed_head_sha: b51d81af7a530739ee1617012bd1b6bb156ecb84
    review_verdict: APPROVE
    reviewer: qfxyyy
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/84#pullrequestreview-5038800008
    merge_commit_sha: 9b17126de6949632128d6bd3841267350c3da231
    review_submitted_at: '2026-08-27T08:35:33Z'
    reviewed_commit_sha: b51d81af7a530739ee1617012bd1b6bb156ecb84
    reviewer_association: COLLABORATOR
    review_api_evidence: https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/84/reviews
    merge_completed_at: '2026-08-27T08:35:52Z'
    ci_evidence: >-
      4/4 GitHub checks succeeded: quality run 33054382531/job 98457401082;
      quality run 33054380144/job 98457392767; persistence-postgresql run
      33054382531/job 98457400750; persistence-postgresql run 33054380144/job
      98457393062.
    human_authorization_evidence: >-
      2026-08-27 user explicitly authorized this TASK-023 active-to-completed
      governance closeout after PR #84 merged.
---

# Objective

实现 MarketGateway 抽象、行情标准化、BarAggregator、MarketQuality 和有界 backpressure，不接 MiniQMT。

## Activation evidence

- 2026-08-26 人类明确批准激活并实施 TASK-023；该授权仅覆盖本任务 backlog → active 治理迁移及任务定义范围内的本地实现与验证。
- 直接依赖 TASK-020 与 TASK-022 均已完成，且分别具有 accepted contract、passed acceptance、正式独立 APPROVE、精确 reviewed Head 与 merge commit 证据。
- 本次激活不授权 MiniQMT/live adapter、Strategy/Order 修改、数据库迁移、部署、发布、推送 GitHub、创建/合并 PR 或 active → completed 收尾。

## Non-goals

- 不实现具体 live-qmt adapter。
- 不实现 Strategy Runtime。
- 不把 Redis 作为行情权威来源。

## Acceptance criteria

- [x] Tick/Bar/Quality/Session 契约测试通过。
- [x] Subscribe/unsubscribe 幂等，callback 只做标准化和有界入队。
- [x] Gap/stale/quality 状态可观测并传播。
- [x] Replay 与 live 输入产生一致标准化事件。

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
- Package or declare an immutable IANA tzdb artifact/version alongside the reviewed schema bundle and load accepted `MARKET_VALIDATION_POLICY` versions by immutable checksum. The production loader must validate the bundle version, exact zone manifest and every TZif digest before activation; it must never fall back to system tzdb. Missing, tampered or unknown zones, unavailable bundle, policy-version checksum collision, stale/future Snapshot evidence, or response-supplied Health threshold mismatch must fail closed in isolated wheel tests.

## Review focus

- 背压是否有界。
- 是否不会阻塞 MiniQMT callback。
- 是否保留行情质量证据。

## Implementation evidence

- 2026-08-26 在隔离分支 `codex/task-023-market-gateway` 上完成本地实现；未接入 MiniQMT，未修改 Strategy、Order、live-qmt、数据库迁移、部署或发布路径。
- `quantiqmt.contracts` 现在从 wheel 内不可变资源加载并校验 reviewed schema bundle 与冻结 tzdb；运行时不读取源码检出的 `spec/contracts/**`，缺失、篡改、摘要不一致、未知时区或策略校验和冲突均 fail closed。
- `quantiqmt.market` 实现契约 DTO 语义校验、MarketGateway 生命周期与订阅幂等、有界入队、显式 overflow/gap 证据、质量状态机、Snapshot/Health 策略验证、确定性 Bar 聚合及 live/replay parity；callback 路径仅执行标准化和有界入队。
- 测试遵循 RED → GREEN：初始测试因缺少 `quantiqmt.market` 与 schema bundle 模块产生 5 个 collection errors，随后通过最小实现满足任务契约。

## Verification evidence

- `poetry run pytest tests/unit/market tests/contract/market tests/integration/market`：18 passed。
- `poetry run pytest tests/contract/messages/test_market_data_contracts.py`：157 passed。
- `poetry run pytest tests/unit/contracts tests/contract/contracts -k "schema_bundle or registry"`：9 passed。
- `poetry build`：sdist 与 wheel 均构建成功。
- `poetry run pytest tests/contract/contracts/test_installed_schema_bundle.py`：4 passed；测试在无源码 checkout、清理 `PYTHONPATH` 的隔离环境安装 wheel，并覆盖 bundle 缺失/篡改失败路径。
- `poetry run mypy src/quantiqmt/market`：9 个 source files 无问题。
- 补充回归 `poetry run pytest tests/unit tests/contract`：855 passed；`poetry run ruff check ...`、`poetry run ruff format --check ...` 与 `poetry run python scripts/validate_specs.py` 全部通过。
- 上述为实现阶段的本地证据；正式独立 Review、GitHub PR、merge 与 completed delivery 的精确证据记录在下方。`release_status` 仍保持 `prohibited`。

## Risks and rollback

- 行情延迟和质量错误必须 fail-visible，不得静默。

## Final review and closeout evidence

- PR #84 was formally approved by independent collaborator `qfxyyy` at
  `2026-08-27T08:35:33Z`, with state `APPROVED` bound to exact reviewed Head
  `b51d81af7a530739ee1617012bd1b6bb156ecb84`:
  https://github.com/qifuxiao/QuantiQmt/pull/84#pullrequestreview-5038800008
  (auditable API record: https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/84/reviews).
- PR #84 merged into `main` as `9b17126de6949632128d6bd3841267350c3da231` at
  `2026-08-27T08:35:52Z`.
- GitHub reports 4/4 successful checks: [quality run 33054382531/job 98457401082](https://github.com/qifuxiao/QuantiQmt/actions/runs/33054382531/job/98457401082), [quality run 33054380144/job 98457392767](https://github.com/qifuxiao/QuantiQmt/actions/runs/33054380144/job/98457392767), [persistence-postgresql run 33054382531/job 98457400750](https://github.com/qifuxiao/QuantiQmt/actions/runs/33054382531/job/98457400750), and [persistence-postgresql run 33054380144/job 98457393062](https://github.com/qifuxiao/QuantiQmt/actions/runs/33054380144/job/98457393062).
- The 2026-08-27 human closeout authorization accepts only TASK-023's merged
  delivery. `release_status` remains `prohibited`; this closeout does not
  authorize MiniQMT/live adapters, deployment, publication, release, or
  activation of TASK-024 or any downstream business task.
