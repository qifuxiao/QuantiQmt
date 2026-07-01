# Event Catalog

> Status: Proposed  
> 本表是事件名称、所有权和路由的唯一目录。新增、删除或改变事件语义必须更新本文并评审兼容性。

事件表示已发生事实；动作请求必须使用 Command。字段定义见 [Event-Payload-Catalog.md](Event-Payload-Catalog.md)，信封与版本规则见 [Message-Contracts.md](Message-Contracts.md)。

## Market Data

| Event | Publisher | Consumers | Partition Key | Persistent | Replay | Payload |
|---|---|---|---|---|---|---|
| market.tick_received.v1 | MarketGateway | StrategyRuntime, MarketQuality | instrument_id | 可选原始库 | Yes | TickPayloadV1 |
| market.bar_closed.v1 | BarAggregator | StrategyRuntime, Storage | instrument_id+interval | Yes | Yes | BarPayloadV1 |
| market.quality_changed.v1 | MarketQuality | StrategyRuntime, Risk, Alert | instrument_id | Yes | Yes | MarketQualityPayloadV1 |
| market.session_changed.v1 | SessionScheduler | StrategyRuntime, Risk, OMS | market | Yes | Yes | SessionPayloadV1 |

Tick 高频流不进入订单审计 Journal；是否持久化由行情存储策略决定。质量与 Session 事件必须持久化。

## Strategy

| Event | Publisher | Consumers | Partition Key | Persistent | Replay | Payload |
|---|---|---|---|---|---|---|
| strategy.signal_generated.v1 | StrategyRuntime | Audit, Analytics | strategy_id | Yes | Yes | SignalPayloadV1 |
| strategy.target_generated.v1 | StrategyRuntime | TargetResolver, Audit | strategy_id | Yes | Yes | StrategyTargetPayloadV1 |
| strategy.target_resolved.v1 | TargetResolver | OrderApplication, Audit | target_id | Yes | Yes | TargetResolvedPayloadV1 |
| strategy.state_changed.v1 | StrategyRuntime | ControlPlane, Alert | strategy_id | Yes | Yes | StrategyStatePayloadV1 |
| strategy.intent_rejected.v1 | OrderApplication | StrategyRuntime, Audit | intent_id | Yes | Yes | IntentRejectedPayloadV1 |

`SignalGenerated` 是策略解释事实，不触发绕过 OMS 的下单。Target 由 TargetResolver 转换为 OrderIntent；直接意图通过 `strategy.submit_order_intent.v1` Command，二者最终都进入相同 OMS/Risk 链路。

## Risk

| Event | Publisher | Consumers | Partition Key | Persistent | Replay | Payload |
|---|---|---|---|---|---|---|
| risk.order_evaluated.v1 | RiskEngine | OrderApplication, Audit, Metrics | order_id | Yes | Yes | RiskDecisionPayloadV1 |
| risk.limit_breached.v1 | RiskEngine | ControlPlane, Alert | scope_id | Yes | Yes | RiskBreachPayloadV1 |
| risk.rule_set_activated.v1 | ConfigService | RiskEngine, Audit | rule_set_id | Yes | Yes | RuleSetActivatedPayloadV1 |

## OMS and Execution

| Event | Publisher | Consumers | Partition Key | Persistent | Replay | Payload |
|---|---|---|---|---|---|---|
| oms.order_registered.v1 | OMS | Risk, Strategy, Audit | order_id | Yes | Yes | OrderRegisteredPayloadV1 |
| oms.order_status_changed.v1 | OMS | Strategy, Portfolio, Audit, Alert | order_id | Yes | Yes | OrderStatusPayloadV1 |
| oms.order_suspended.v1 | OMS | Reconciliation, ControlPlane, Alert | order_id | Yes | Yes | OrderSuspendedPayloadV1 |
| execution.attempt_started.v1 | ExecutionEngine | OMS, Audit | order_id | Yes | Yes | ExecutionAttemptPayloadV1 |
| execution.outcome_unknown.v1 | ExecutionEngine | OMS, Reconciliation, Alert | order_id | Yes | Yes | UnknownOutcomePayloadV1 |
| broker.order_reported.v1 | BrokerAdapter | OMS, Reconciliation, Audit | order_id/client_order_id | Yes | Yes | BrokerOrderPayloadV1 |
| broker.trade_reported.v1 | BrokerAdapter | OMS, Reconciliation, Audit | order_id/client_order_id | Yes | Yes | TradePayloadV1 |

Broker Event 允许重复和乱序；消费者必须依赖 message_id、业务唯一键和 aggregate_version 幂等归并。

## Account, Portfolio and Ledger

| Event | Publisher | Consumers | Partition Key | Persistent | Replay | Payload |
|---|---|---|---|---|---|---|
| ledger.trade_posted.v1 | AccountLedger | Portfolio, Risk, Audit | account_id | Yes | Yes | LedgerTransactionPayloadV1 |
| ledger.adjustment_posted.v1 | AccountLedger | Portfolio, Risk, Audit | account_id | Yes | Yes | LedgerTransactionPayloadV1 |
| portfolio.position_changed.v1 | PortfolioProjection | Risk, Strategy, API | account_id+instrument_id | Yes | Yes | PositionPayloadV1 |
| portfolio.snapshot_created.v1 | PortfolioProjection | Recovery, Risk | account_id | Yes | Yes | PortfolioSnapshotPayloadV1 |
| account.snapshot_observed.v1 | BrokerAdapter | Reconciliation, Risk | account_id | Yes | Yes | AccountSnapshotPayloadV1 |
| portfolio.snapshot_observed.v1 | BrokerAdapter | Reconciliation, Risk | account_id | Yes | Yes | BrokerPositionSnapshotPayloadV1 |

## Recovery, Operations and Observability

| Event | Publisher | Consumers | Partition Key | Persistent | Replay | Payload |
|---|---|---|---|---|---|---|
| reconciliation.case_opened.v1 | Reconciliation | ControlPlane, Alert | case_id | Yes | Yes | ReconciliationCasePayloadV1 |
| reconciliation.case_resolved.v1 | Reconciliation | OMS, Ledger, Audit | case_id | Yes | Yes | ReconciliationResolvedPayloadV1 |
| system.mode_changed.v1 | TradingCore | All trading components | system/account scope | Yes | Yes | SystemModePayloadV1 |
| system.component_health_changed.v1 | HealthService | ControlPlane, Alert | component_id | Yes | Yes | HealthPayloadV1 |
| system.kill_switch_changed.v1 | ControlPlane | Risk, OMS, Execution, Audit | scope_id | Yes | Yes | KillSwitchPayloadV1 |
| config.version_activated.v1 | ConfigService | Affected components, Audit | config_scope | Yes | Yes | ConfigActivatedPayloadV1 |

## 发布约束

- Domain Event 与聚合更新、Outbox 在同一事务提交。
- Integration Event 只有对应事实提交后才可发布。
- 一个 Publisher 是语义所有者；其他模块不能发布同名事件。
- Consumers 是允许列表。新增副作用型 Consumer 必须评审，报表/指标型 Consumer 可按治理流程登记。
- Replay 时默认禁用 Broker、通知和人工操作等外部副作用 Consumer。
