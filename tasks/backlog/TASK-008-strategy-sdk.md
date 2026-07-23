---
id: TASK-008
title: Implement strategy SDK and isolated runtime contract
status: blocked
depends_on: [TASK-002, TASK-016]
spec_refs: [PORTS-STRATEGY, SM-STRATEGY, CONTRACT-STRATEGY-TARGET-V1, CONTRACT-STRATEGY-CONTEXT-V1, CONTRACT-STRATEGY-CALLBACK-V1, CONTRACT-STRATEGY-OUTPUT-V1, CONTRACT-STRATEGY-CHECKPOINT-V1, REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths: [src/quantiqmt/strategy_sdk/**, src/quantiqmt/strategy_runtime/**, tests/contract/strategy/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/order/infrastructure/**]
verification:
  commands: ["poetry run pytest tests/contract/strategy", "poetry run mypy src/quantiqmt/strategy_sdk src/quantiqmt/strategy_runtime"]
---

# Objective

实现 Strategy Protocol、只读 Context、Checkpoint 和 Runtime 状态/资源边界。

## Blocking reason

需要 TASK-016 冻结 StrategyContext DTO、callback event payload、checkpoint envelope/checksum、generation fencing、resource limits、output validation 和 runtime failure semantics；这些契约现已冻结，待 TASK-016 独立 Review/合并后解除本任务阻塞。

## Non-goals

- 不实现具体交易策略。
- 不连接 Broker、数据库、Redis、OMS Repository 或平台 Secret。
- 不实现 TargetResolver；策略只能输出 Target 或 OrderIntent。

## Acceptance criteria

- [ ] SDK 不暴露 Broker、DB、Redis、OMS Repository。
- [ ] 只有 RUNNING generation 能输出。
- [ ] 回调串行、deadline 有界，异常使策略 PAUSED/ERROR。
- [ ] Checkpoint 校验版本/checksum，重复事件处理幂等。
- [ ] Import boundary tests 证明 strategy package 不能依赖 trading platform/infrastructure。
- [ ] Resource-limit tests 覆盖 callback timeout、输出频率和旧 generation 输出拒绝，按 `NFR-RELIABILITY.strategy_runtime` 的有限值验证。

## Frozen implementation boundary

- SDK 仅依赖 `CONTRACT-STRATEGY-CONTEXT-V1`、`CONTRACT-STRATEGY-CALLBACK-V1`、`CONTRACT-STRATEGY-OUTPUT-V1` 和 `CONTRACT-STRATEGY-CHECKPOINT-V1`；不得读取 checkout `spec/**`。
- Runtime 必须串行派发 callback、执行绝对 deadline、校验 scope/schema/frequency/generation，并把 Target/OrderIntent 分别交给 TargetResolver/OMS 注册链路。
- Restore、资源超限、异常和过期依赖必须 fail-closed，并按 `SM-STRATEGY` 转换 PAUSED/ERROR；任何失败不得改变 OMS 订单。

## Review focus

- StrategyContext 是否只读且版本化。
- Runtime 是否能隔离单策略崩溃。
- 是否存在绕过 TargetResolver/OMS/Risk 的下单路径。

## Risks and rollback

- Strategy SDK 是策略团队入口，任何越权 API 都会成为长期安全债务。
