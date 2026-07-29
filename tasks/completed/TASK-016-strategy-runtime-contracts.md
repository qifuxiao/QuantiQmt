---
id: TASK-016
title: Complete Strategy SDK and runtime L4 contracts
status: completed
depends_on: [TASK-014]
spec_refs: [INV-TRADING, PORTS-STRATEGY, SM-STRATEGY, CONTRACT-STRATEGY-TARGET-V1, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/state-machines/**, spec/workflows/**, spec/nfr/**, tasks/backlog/TASK-008-strategy-sdk.md, tasks/backlog/TASK-016-strategy-runtime-contracts.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: not_applicable
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: merged_contract_followup
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/41
    reviewed_head_sha: 987a5b91d2284fb21017a16070b41a1bfd3cfc18
    review_verdict: APPROVE
    reviewer: qifuxiao
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/41#pullrequestreview-4803608047
    merge_commit_sha: 01d6cd12eb8a682780b58218a91d19adbc8f90fa
    human_authorization_evidence: human-authorized TASK-016 active-to-completed governance closeout after PR #41 merge
---

# Objective

冻结 Strategy SDK、StrategyContext、Callback events、Checkpoint、generation fencing、资源限制和 Runtime 状态语义，使 TASK-008 可以安全实现。

## Non-goals

- 不实现 Strategy SDK 或具体策略。
- 不实现 MarketGateway、TargetResolver 或 OMS。
- 不暴露 Broker、DB、Redis、Repository 或平台 Secret。

## Acceptance criteria

- [x] 定义 StrategyContext 只读 DTO、snapshot version、权限 scope 和 Live/Backtest 一致性约束。
- [x] 定义 on_market/on_timer/on_order/on_trade callback 输入与 deadline。
- [x] 定义 StrategyOutput、Target/OrderIntent 输出校验、频率限制和 generation fencing。
- [x] 定义 Checkpoint envelope、schema_version、checksum、restore 失败行为。
- [x] 定义 Runtime 资源限制、异常处理、PAUSED/ERROR 转换和审计事件。
- [x] 更新 TASK-008，使其可直接实现并验证。

## Evidence

- Added machine-validated Context, Callback, Output and Checkpoint schemas and registered them in `spec/manifest.yaml`.
- PORTS-STRATEGY now freezes read-only snapshot/version semantics, least-privilege scopes, callback deadlines, schema-first output validation, generation fencing, checkpoint checksum/restore fail-closed behavior, resource limits and audit transitions.
- SM-STRATEGY and WF-STRATEGY-RUNTIME define PAUSED/ERROR transitions, serial bounded callbacks, immutable verified runtime artifacts and the no-source-checkout-spec rule.
- TASK-008 now references the frozen contracts and has a direct implementation boundary.
- Review follow-up: output Target/OrderIntent refs use registered canonical command URNs and reject arbitrary/null typed payloads; `strategy.state_changed.v1` is schema-registered with constrained states/reasons; BACKTEST requires non-null `backtest_end`; `initialize` is a callback type; checkpoint hashing is fixed to RFC 8785 JCS UTF-8 payload-only SHA-256.
- Latest main synchronization includes TASK-029/TASK-030 governance; manifest 0.7.0 compatibility, migration, affected tasks and deployment order now preserve their blocked/active boundaries.
- TASK-016 remained `active` until PR #41 received independent APPROVE and merged; this separate human-authorized governance PR records the completed state.

### Governance completion evidence

- PR #41 Head: `987a5b91d2284fb21017a16070b41a1bfd3cfc18`.
- PR #41 merge commit / latest `origin/main`: `01d6cd12eb8a682780b58218a91d19adbc8f90fa`.
- Independent APPROVE was published by `qifuxiao` with verdict `APPROVE`, review commit `987a5b91d2284fb21017a16070b41a1bfd3cfc18`, bound to the reviewed Head: [PR #41](https://github.com/qifuxiao/QuantiQmt/pull/41), [review](https://github.com/qifuxiao/QuantiQmt/pull/41#pullrequestreview-4803608047).
- CI completed 4/4 successfully: [quality](https://github.com/qifuxiao/QuantiQmt/actions/runs/30416579583/job/90464297221), [quality](https://github.com/qifuxiao/QuantiQmt/actions/runs/30416577593/job/90464291293), [persistence-postgresql](https://github.com/qifuxiao/QuantiQmt/actions/runs/30416579583/job/90464297257), [persistence-postgresql](https://github.com/qifuxiao/QuantiQmt/actions/runs/30416577593/job/90464291209).
- Local gates passed: specification validation, 195 spec/contract tests, 72 risk tests, mypy, ruff, format check, diff check and schema probes.
- TASK-016 closeout does not release or activate TASK-008: `strategy.state_changed.v1` remains planned, TASK-008 lacks Market readiness, and `release_status=prohibited`; follow-up remediation is delegated to TASK-031 deviation work.
- This active-to-completed migration is explicitly authorized by human project members after PR #41 merge; no contract or business implementation is changed here.

## Review focus

- 策略是否无法越权访问交易平台内部。
- 单策略崩溃是否不会影响 OMS/Execution。
- Backtest 是否不能暴露未来数据。

## Risks and rollback

- SDK 是外部策略团队入口；越权接口一旦发布很难收回。
