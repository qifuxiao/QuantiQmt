# Monitoring Specification

> Status: Proposed  
> 指标采用 Prometheus 命名；单位写入 suffix。实际阈值须经容量测试校准，不能删除规定的安全告警。

## 公共 Labels

允许：`service, instance, environment, broker, account_group, strategy_type, result, error_category`。禁止将 order_id、trade_id、instrument_id、correlation_id、完整 account_id 作为常驻 label；它们进入日志/Trace。

## 延迟指标

| Metric | Type | 说明 |
|---|---|---|
| quantiqmt_market_ingress_latency_seconds | Histogram | source_time→gateway receive |
| quantiqmt_market_normalize_duration_seconds | Histogram | 行情标准化耗时 |
| quantiqmt_strategy_evaluation_duration_seconds | Histogram | 单次策略决策 |
| quantiqmt_risk_evaluation_duration_seconds | Histogram | 全规则风险决策 |
| quantiqmt_oms_command_duration_seconds | Histogram | OMS Command 处理 |
| quantiqmt_execution_dispatch_duration_seconds | Histogram | approved→Broker 调用开始 |
| quantiqmt_broker_request_duration_seconds | Histogram | SDK/API 请求耗时 |
| quantiqmt_order_end_to_end_latency_seconds | Histogram | intent→Broker 确认/首回报 |
| quantiqmt_trade_accounting_latency_seconds | Histogram | Trade receive→Ledger committed |
| quantiqmt_event_processing_duration_seconds | Histogram | Consumer handler 耗时 |

## 流量与结果

| Metric | Type |
|---|---|
| quantiqmt_market_events_total | Counter |
| quantiqmt_order_intents_total | Counter |
| quantiqmt_orders_registered_total | Counter |
| quantiqmt_risk_decisions_total{result} | Counter |
| quantiqmt_broker_commands_total{operation,result} | Counter |
| quantiqmt_broker_reports_total{type} | Counter |
| quantiqmt_trades_recorded_total | Counter |
| quantiqmt_order_state_transitions_total{from,to} | Counter |
| quantiqmt_errors_total{error_category,error_family} | Counter |

## 队列、消息与一致性

| Metric | Type | 告警方向 |
|---|---|---|
| quantiqmt_queue_depth | Gauge | 高水位 |
| quantiqmt_queue_oldest_age_seconds | Gauge | 消费停滞 |
| quantiqmt_queue_dropped_total{policy} | Counter | 订单队列任何 drop=P0 |
| quantiqmt_outbox_unpublished | Gauge | 积压 |
| quantiqmt_outbox_oldest_age_seconds | Gauge | 发布延迟 |
| quantiqmt_inbox_duplicates_total | Counter | 异常突增 |
| quantiqmt_stream_pending | Gauge | PEL 积压 |
| quantiqmt_dead_letter_total | Counter | 任何核心消息=P1 |
| quantiqmt_order_unknown | Gauge | >0 持续=P1 |
| quantiqmt_reconciliation_open{severity} | Gauge | P0/P1 按级别告警 |
| quantiqmt_projection_lag_events | Gauge | 风控新鲜度 |

## 健康与资源

`quantiqmt_component_health{component,state}`、`quantiqmt_broker_connected`、`quantiqmt_leader_fencing_token`、`quantiqmt_config_active_version_info`、`quantiqmt_clock_offset_seconds`、`process_cpu_seconds_total`、`process_resident_memory_bytes`、GC pause、event loop lag、线程/Task 数和 DB/Redis 连接池使用率。

## 业务风险指标

`quantiqmt_exposure_amount`、`quantiqmt_available_cash`、`quantiqmt_risk_limit_utilization_ratio`、`quantiqmt_daily_pnl_amount`、`quantiqmt_active_orders`、`quantiqmt_cancel_ratio`。账户标签必须脱敏或映射为有限 account_group。

## 告警规则

| Alert | 条件示例 | 级别 | 自动动作 |
|---|---|---|---|
| DualOmsLeader | 同 scope 出现不同 fencing writer | P0 | Adapter 拒绝旧 token，HALTED |
| OrderMessageDropped | 核心队列 drop 增量 > 0 | P0 | SAFE |
| AuditUnavailable | 审计/Journal 写失败 | P0 | 禁止新单 |
| UnknownOrderStuck | UNKNOWN 超过可见性窗口 | P1 | SAFE scope + 对账 |
| BrokerDisconnected | 交易时段连接断开 | P1 | 禁止新单、重连 |
| ReconciliationDifference | P0/P1 Case > 0 | 对应级别 | SAFE/HALTED |
| MarketStale | freshness 超阈值 | P1/P2 | 暂停相关策略 |
| QueueHighWatermark | depth >80% 持续窗口 | P2 | 背压/降级 |
| LatencySloBurn | P99/SLO burn rate 超阈值 | P2 | 限流/调查 |
| ConfigVersionMismatch | 必要组件 active version 不一致 | P1 | 禁止相关新单 |

## Dashboard

至少提供：Trading Overview、Order Funnel、Latency Breakdown、Queues/Streams、Broker Health、Risk/Exposure、Reconciliation、Database/Redis、Strategy Health、Recovery Dashboard。每个 P0/P1 告警链接对应 Runbook 和相关 Trace/日志查询。
