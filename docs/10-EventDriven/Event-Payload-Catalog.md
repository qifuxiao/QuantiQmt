# Event Payload Catalog

> Status: Proposed  
> 以下是规范性 Payload V1。所有事件还必须携带 Message Envelope V1。

## 通用规则

- `symbol` 统一使用 `instrument_id`；格式由 InstrumentSpec 管理。
- `timestamp` 拆分为语义明确的 `occurred_at/trade_time/report_time`。
- Money/Price/Quantity 遵守 [Python 技术基线](../00-Architecture/04-Python-Technical-Baseline.md)。
- `strategy_id` 只在确有订单归属时出现；外部手工订单可为空并由对账导入。

## Market Payloads

### TickPayloadV1

`instrument_id, exchange, trading_day, source_sequence?, source_time, receive_time, last_price, bid_prices[], bid_quantities[], ask_prices[], ask_quantities[], volume, turnover, open_interest?, quality, source`

约束：买卖档位数组长度匹配；价格和数量非负；source_sequence 存在时同来源单调递增。

### BarPayloadV1

`instrument_id, exchange, interval, window_start, window_end, open, high, low, close, volume, turnover, source_event_count, completeness`

### MarketQualityPayloadV1

`instrument_id, previous_quality, current_quality, reason_codes[], last_good_sequence?, gap_range?, detected_at`

## Strategy Payloads

### SignalPayloadV1

`signal_id, strategy_id, strategy_version, instrument_id, signal_type, strength?, target_quantity?, target_weight?, generated_at, market_data_version, parameter_set_version, explanation?`

Signal 不含 Broker 路由，不代表已批准订单。

### StrategyStatePayloadV1

`strategy_id, from_state, to_state, reason_code, checkpoint_version?, changed_at, operator_id?`

### StrategyTargetPayloadV1

`target_id, target_type(WEIGHT/POSITION), strategy_id, strategy_version, portfolio_or_account_scope, instrument_id, target_weight?, target_quantity?, effective_at, valid_until, decision_id, input_event_id, constraints, reason_code`

WEIGHT 必须提供 target_weight；POSITION 必须提供 target_quantity。相同 target_id 表示同一目标，重复消费不得生成重复订单。

### TargetResolvedPayloadV1

`resolution_id, target_id, strategy_id, input_snapshot_versions, target_quantity, current_quantity, active_order_expected_delta, resolved_delta, rounding_adjustment, result(INTENT/NO_ACTION/REJECTED), intent_id?, reason_code, resolved_at`

## Risk Payloads

### RiskDecisionPayloadV1

`decision_id, order_id, order_version, decision, rule_set_version, account_snapshot_version, portfolio_snapshot_version, market_snapshot_version, results[], evaluated_at, total_latency_us`

`results[]`：`rule_id, result, reason_code, measured_value?, limit_value?, latency_us`。

### RiskBreachPayloadV1

`breach_id, scope_type, scope_id, rule_id, severity, measured_value, limit_value, action, detected_at`

## Order and Execution Payloads

### OrderRegisteredPayloadV1

`order_id, intent_id, account_id, strategy_id?, instrument_id, side, position_effect, order_type, quantity, limit_price?, time_in_force, client_order_id, registered_at`

### OrderStatusPayloadV1

`order_id, from_status, to_status, reason_code, broker_order_id?, cum_quantity, leaves_quantity, average_price?, source_report_id?, changed_at`

### ExecutionAttemptPayloadV1

`attempt_id, order_id, client_order_id, broker, account_id, fencing_token, attempt_number, started_at, deadline_at`

### UnknownOutcomePayloadV1

`attempt_id, order_id, operation, timeout_at, last_known_connection_state, reconciliation_deadline, reason_code`

### BrokerOrderPayloadV1

`broker, account_id, trading_day, client_order_id?, broker_order_id, instrument_id, broker_status, original_quantity, cum_quantity, leaves_quantity, average_price?, broker_sequence?, report_time, received_at, raw_error_code?, raw_error_message?`

### TradePayloadV1

`broker, account_id, trading_day, trade_id, order_id?, client_order_id?, broker_order_id, instrument_id, side, position_effect, price, quantity, commission?, tax?, trade_time, broker_sequence?, received_at`

Slippage 不属于 Broker 成交事实，应由 Analytics 基于指定基准另行计算，不能写入 `broker.trade_reported.v1` 原始事实。

## Portfolio and Ledger Payloads

### PositionPayloadV1

`account_id, instrument_id, previous_quantity, current_quantity, available_quantity, frozen_quantity, average_cost, realized_pnl, unrealized_pnl?, projection_version, as_of`

### LedgerTransactionPayloadV1

`transaction_id, account_id, business_type, reference_type, reference_id, entries[], effective_at, recorded_at`

`entries[]`：`ledger_account, currency, direction, amount`；同币种借贷必须平衡。

### AccountSnapshotPayloadV1

`broker, account_id, trading_day, currency, total_assets, cash_balance, available_cash, frozen_cash, margin?, snapshot_version, quality, as_of, checksum`

### BrokerPositionSnapshotPayloadV1

`broker, account_id, trading_day, positions[], snapshot_version, quality, as_of, checksum`；position 包含 instrument_id、total/available/frozen quantity、average_cost?。

## Operations Payloads

### SystemModePayloadV1

`scope_type, scope_id, from_mode, to_mode, reason_code, triggered_by, changed_at, approval_id?`

### HealthPayloadV1

`component_id, component_type, from_state, to_state, checks[], changed_at`；check 包含 name、status、latency_ms?、detail_code。

### KillSwitchPayloadV1

`scope_type, scope_id, enabled, cancel_active_orders, reason, operator_id, approval_id?, changed_at`

### ReconciliationCasePayloadV1

`case_id, difference_type, severity, account_id, order_id?, local_evidence, broker_evidence, proposed_action?, opened_at`

## Payload 变更门禁

每个 Payload 必须提供 valid、minimal、maximal、invalid 和 unknown-enum golden fixture。契约测试验证序列化往返、精度、时区、兼容性及缺失必填字段失败行为。
