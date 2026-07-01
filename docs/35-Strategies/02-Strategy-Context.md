# StrategyContext

> Status: Proposed

StrategyContext 是策略可见世界的只读、版本化快照，不能成为访问平台内部服务的 Service Locator。

## 允许内容

| 能力 | 返回值 | 约束 |
|---|---|---|
| clock | Clock view | Live/Backtest 可替换；禁止系统时间 |
| market | MarketSnapshot | 包含 as_of、quality、version |
| position | StrategyPositionView | 按 strategy attribution 或批准的 portfolio scope |
| account | AccountRiskView | 只读、脱敏、包含 freshness |
| active_orders | OrderView[] | 只读，至少包含预期未成交影响 |
| parameters | Immutable ParameterSet | 单次决策固定 version |
| calendar | TradingCalendarView | session、trading_day |
| benchmark/reference | Versioned data view | 必须声明数据版本 |
| logger/diagnostics | 结构化、有限速接口 | 不得改变业务状态 |

## 禁止内容

- Broker/Market Gateway 实例或凭证。
- OMS/Repository/UnitOfWork。
- SQL、Redis、HTTP 通用客户端。
- 可变 Account/Portfolio/Order 聚合。
- 任意动态导入和不受控文件系统写入。

## Snapshot 一致性

每次策略决策获得一个 DecisionContext：

```text
context_version
market_snapshot_version
portfolio_snapshot_version
account_snapshot_version
parameter_version
rule/permission metadata
created_at / freshness
```

Runtime 不承诺跨来源强事务快照，但必须标记各版本和 freshness。策略可以拒绝产生输出；平台 Risk 对陈旧或不一致快照再次 fail-closed。

## 订单视图

active_orders 用于避免重复目标，包含 order_id、instrument、side、original/cum/leaves quantity、status 和 expected_position_effect。策略不得根据本地回调自行假设订单已成交。

## 回测一致性

LiveContext 与 BacktestContext 实现同一只读契约。Backtest 不得额外暴露未来 Bar、下一 Tick、完整当日收盘或最终成交信息。

## Context 权限

策略 manifest 声明 scope。Runtime 对账户、标的、数据集和字段执行最小权限；策略不能通过遍历 API 获取未授权账户或其他策略私有状态。
