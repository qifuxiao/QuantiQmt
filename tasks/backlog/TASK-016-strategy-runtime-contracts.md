---
id: TASK-016
title: Complete Strategy SDK and runtime L4 contracts
status: active
depends_on: [TASK-014]
spec_refs: [INV-TRADING, PORTS-STRATEGY, SM-STRATEGY, CONTRACT-STRATEGY-TARGET-V1, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/state-machines/**, spec/workflows/**, spec/nfr/**, tasks/backlog/TASK-008-strategy-sdk.md, tasks/backlog/TASK-016-strategy-runtime-contracts.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
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
- TASK-016 remains `active`; completion still requires independent Review and human governance migration.

## Review focus

- 策略是否无法越权访问交易平台内部。
- 单策略崩溃是否不会影响 OMS/Execution。
- Backtest 是否不能暴露未来数据。

## Risks and rollback

- SDK 是外部策略团队入口；越权接口一旦发布很难收回。
