# Strategy SDK Contract

> Status: Proposed  
> Strategy SDK 是策略团队唯一允许使用的平台编程入口。

## Strategy 接口

```python
class Strategy(Protocol):
    def initialize(self, context: StrategyContext) -> None: ...
    def on_market(self, event: MarketEvent, context: StrategyContext) -> StrategyDecision: ...
    def on_timer(self, event: TimerEvent, context: StrategyContext) -> StrategyDecision: ...
    def on_order(self, event: OrderEvent, context: StrategyContext) -> None: ...
    def on_trade(self, event: TradeEvent, context: StrategyContext) -> None: ...
    def checkpoint(self) -> StrategyCheckpoint: ...
    def restore(self, checkpoint: StrategyCheckpoint) -> None: ...
```

接口为逻辑签名，具体事件类型必须引用版本化 contracts。回调不得直接执行网络、数据库或 Broker I/O。

## StrategyDecision

一次回调返回不可变结果：

```text
decision_id
strategy_id / strategy_version
input_event_id
generated_at
outputs: TargetWeight | TargetPosition | OrderIntent
state_changes
diagnostics
```

空决策使用显式 `NoAction`，不能以异常或 `None` 模糊表达。

## 初始化与恢复

- initialize 只验证参数、声明订阅和创建纯内存状态，不连接基础设施。
- restore 必须校验 strategy_id、strategy_version、state_schema_version 和 checksum。
- 初始化/恢复完成后进入 READY，不自动进入 RUNNING。
- restore 不得重放产生真实交易副作用；历史追赶由 Runtime 设置 replay mode。

## 回调语义

- 同一策略实例的回调默认串行，避免策略自行加锁。
- on_market 必须在配置的 deadline 内完成；超时会暂停该策略。
- on_order/on_trade 可能重复，策略按 event_id 幂等更新本地派生状态。
- Runtime 不保证不同标的全局顺序，只保证声明 partition 内顺序。
- 回调异常由 Runtime 捕获并转为 StrategyError；禁止吞掉异常继续交易。

## 订阅声明

策略通过 manifest 声明，而非在任意位置调用 Gateway：

```text
market subscriptions: instruments, data_type, interval, depth
timers: schedule, trading calendar, misfire policy
order/trade scope: own strategy_id or approved shared portfolio
required snapshots: account, position, benchmark
```

Runtime 验证 manifest 与账户、环境和资源策略。

## Checkpoint

包含 strategy_id、strategy_version、state_schema_version、parameter_version、last_input_position、payload、created_at、checksum。Checkpoint 必须可迁移或明确拒绝旧版本；不得 pickle 未受控对象。

## 禁止 API

SDK 不提供 `buy/sell/submit_order/cancel_all/get_broker/db_session/redis_client`。撤单需求通过受限 `CancelIntent` 输出，仍由 Order Application 和 OMS 处理。

## SDK 兼容

SDK 遵循语义化版本。破坏性变更升级 major，并提供至少一个发布周期的适配层。每个策略制品声明 sdk_version_range，部署前执行兼容检查。
