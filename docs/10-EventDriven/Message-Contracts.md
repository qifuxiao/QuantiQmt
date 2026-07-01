# 消息与数据契约

> Status: Proposed  
> 本文是实现前必须冻结的逻辑契约；Python 类型和序列化实现必须与此一致。

## 基础类型

| 类型 | 规则 |
|---|---|
| ID | ULID/UUID 字符串，大小写规范化，不复用 |
| 时间 | UTC、带时区 ISO-8601；持久化使用 PostgreSQL `timestamptz` |
| 交易日 | `YYYY-MM-DD`，由交易日历决定，不从 UTC 日期推导 |
| 价格 | `Decimal` 或按品种定义的整数 tick，不使用二进制 float 做资金结算 |
| 数量 | 整数；若资产支持小数，使用带 scale 的 Decimal |
| 金额 | `Decimal`，显式 currency 和 scale |
| 枚举 | 稳定字符串；未知值进入兼容分支，不按序号序列化 |

## Message Envelope V1

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| message_id | ID | 是 | 全局唯一，Inbox 去重键 |
| message_type | string | 是 | `{domain}.{name}.v{n}` |
| schema_version | int | 是 | 从 1 递增 |
| occurred_at | datetime | 是 | 来源发生时间 |
| received_at | datetime | 是 | 当前系统首次接收时间 |
| correlation_id | ID | 是 | 一次业务链；行情 fan-out 后每个意图生成独立链 |
| causation_id | ID | 否 | 直接触发本消息的 message_id |
| aggregate_id | ID | 否 | 聚合消息必填 |
| aggregate_version | int | 否 | 聚合事件必填，严格递增 |
| source | string | 是 | service/instance |
| partition_key | string | 是 | 订单链使用 order_id |
| idempotency_key | string | Command 必填 | 同一业务动作重试时不变 |
| payload | object | 是 | 由 message_type 定义 |

## 核心 Command

### `strategy.submit_target.v1`

包含 TargetWeight 或 TargetPosition、strategy/version、scope、decision_id、input_event_id、effective_at 和 valid_until。TargetResolver 按 target_id 幂等处理；目标过期、scope 越权或快照不可用时返回明确拒绝/NoAction，不直接调用 Broker。

### `strategy.submit_order_intent.v1`

| 字段 | 类型 | 说明 |
|---|---|---|
| intent_id | ID | 幂等主键 |
| strategy_id/strategy_version | string | 策略身份与版本 |
| account_id | string | 目标账户 |
| instrument_id | string | 规范化证券代码 |
| side | BUY/SELL | 方向 |
| position_effect | OPEN/CLOSE/AUTO | 股票可使用 AUTO |
| order_type | LIMIT/MARKET/BEST | Broker 不支持时拒绝 |
| quantity | Quantity | 严格大于零 |
| limit_price | Price? | LIMIT 必填 |
| time_in_force | DAY/IOC/FOK | 能力矩阵校验 |
| signal_time/market_data_version | datetime/string | 风险新鲜度判断 |
| tags | map<string,string> | 限长、不得放敏感信息 |

结果只能是 `OrderRegistered` 或确定性 `IntentRejected`；超时后调用方按 intent_id 查询，不能生成新 ID 重试。

### `risk.evaluate_order.v1`

包含 order_id、order_version、完整订单快照引用、account_snapshot_version、portfolio_snapshot_version、market_snapshot_version、rule_set_version。Risk 只能返回决策，不能修改订单。

### `oms.apply_risk_decision.v1`

包含 order_id、expected_order_version、decision_id、decision(PASS/REJECT)、rule_set_version、reason_codes。版本不匹配返回 `VERSION_CONFLICT`，由 Application 重新读取后决定是否重评。

### `execution.submit_order.v1`

包含 order_id、client_order_id、broker/account、已批准订单参数、approved_order_version 和 fencing_token。Adapter 必须拒绝缺少或过期 fencing_token 的请求。

### `execution.cancel_order.v1`

包含 order_id、client_order_id、broker_order_id（若已知）、cancel_request_id、expected_order_version、fencing_token。重复请求使用相同 cancel_request_id。

## 核心 Event

### `oms.order_registered.v1`

包含 order_id、intent_id、订单不可变初始参数、owner_strategy_id、registered_at。

### `risk.order_evaluated.v1`

包含 decision_id、order_id、decision、rule_set_version、snapshot_versions、逐规则结果 `{rule_id, result, reason_code, measured_value, limit_value, latency_us}`。

### `broker.order_reported.v1`

包含 broker、account_id、trading_day、client_order_id、broker_order_id、broker_status、cum_quantity、leaves_quantity、average_price、broker_sequence、report_time、raw_error_code。原始 payload 可加密归档，但不能进入 Domain。

### `broker.trade_reported.v1`

包含 broker、account_id、trading_day、trade_id、broker_order_id、instrument_id、side、quantity、price、commission、trade_time、broker_sequence。去重键为 `(broker, account_id, trading_day, trade_id)`。

### `oms.order_status_changed.v1`

包含 order_id、from_status、to_status、reason_code、source_report_id、cum_quantity、leaves_quantity。`aggregate_version` 决定订单内顺序。

### `account.snapshot_observed.v1` / `portfolio.snapshot_observed.v1`

快照包含 source、as_of、trading_day、snapshot_version、currency/positions、quality(FRESH/STALE/PARTIAL)、checksum。PARTIAL 快照不得用于放行依赖完整资金或持仓的风险规则。

## 错误模型

统一错误字段：`error_code`、`category`、`retryability`、`message`、`details`、`source`。

| category | 例子 | 默认动作 |
|---|---|---|
| VALIDATION | 参数/能力不支持 | 不重试 |
| BUSINESS | 风控拒绝、非法迁移 | 不重试，审计 |
| CONFLICT | 版本冲突、重复映射 | 重新读取/人工处置 |
| TRANSIENT | 连接重置、限流 | 在预算内重试 |
| UNKNOWN_OUTCOME | 下单超时 | 查询与对账，禁止盲重试 |
| DEPENDENCY | DB/Redis 不可用 | 熔断、降级/SAFE |
| INTERNAL | 未分类异常 | 隔离消息、P1 告警 |

## 版本兼容

- 同一版本只允许新增可选字段和扩展枚举兼容处理。
- 删除、改名、改变含义或精度必须发布新 message_type 版本。
- Producer 至少支持当前版本；Consumer 在滚动升级期支持当前和前一版本。
- 契约样例保存为 golden fixtures，所有 Adapter 执行编码/解码契约测试。
