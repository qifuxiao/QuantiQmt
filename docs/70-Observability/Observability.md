# 可观测性与审计

> Status: Proposed

## 三条链

- 业务审计链：不可变地回答谁在何时因何规则发起、批准、拒绝、发送和修复订单。
- 分布式追踪链：通过 correlation_id/causation_id 串联 Market → Strategy → Risk → OMS → Broker → Trade。
- 运行监控链：指标和日志说明容量、延迟、错误与依赖健康。

## 日志

使用结构化 JSON；至少包含 timestamp、level、service、instance、environment、message、correlation_id、order_id、strategy_id、account_id、error_code。禁止记录密码、Token、完整个人信息或未脱敏凭证。热路径异步写日志，但审计日志不得静默丢弃。

## 指标

| 类别 | 关键指标 |
|---|---|
| 延迟 | market_ingress、strategy、risk、oms、broker_request 的 histogram |
| 流量 | ticks、intents、orders、trades、rejects、cancels |
| 队列 | depth、oldest_age、drop/coalesce_count |
| 正确性 | duplicate、out_of_order、reconciliation_difference、unknown_order |
| 依赖 | connection_state、error_rate、timeout、circuit_state |
| 业务 | exposure、available_cash、limit_utilization、daily_pnl |

高基数字段（order_id、symbol）原则上不做 Prometheus label，进入日志/Trace。

## 告警等级

- P0：可能失控下单、双 Leader、账务严重不一致；自动 Kill Switch 并立即响应。
- P1：交易核心不可用、订单 UNKNOWN 持续、Broker 断连；分钟级响应。
- P2：策略暂停、行情陈旧、队列高水位；交易时段内处理。
- P3：容量趋势、非关键任务失败；工作时间处理。

每条告警必须包含影响、证据、Runbook、抑制/聚合规则和恢复条件，禁止仅凭“进程存在”自动恢复交易。

## 交易链验收

输入 correlation_id 后，应能查到行情摘要、策略版本和决策、OrderIntent、风险规则结果、OMS 全部迁移、Broker 请求/回报、成交、账本分录及任何人工操作。
