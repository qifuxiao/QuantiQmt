# 核心逻辑 Schema 与数据库约束

> Status: Proposed  
> 本文定义逻辑字段和约束；物理 DDL 在实现评审时生成，不能削弱这些约束。

## orders

主键 `order_id`；唯一键 `intent_id`、`client_order_id`，broker_order_id 在 `(broker, account_id, trading_day)` 范围唯一。包含 status、version、原始订单参数、owner_strategy_id、risk_decision_id、cum/leaves quantity、created/updated_at。更新使用 `WHERE order_id=? AND version=?` 乐观锁。

约束：quantity > 0；0 ≤ cum_quantity ≤ quantity；leaves_quantity ≥ 0；LIMIT 必须有 limit_price；终态不能被普通命令修改。

## order_journal

追加表：`(order_id, aggregate_version)` 唯一，message_id 唯一；保存 event_type、payload、occurred_at、recorded_at、correlation/causation_id、checksum。禁止 UPDATE/DELETE，数据修正通过新事件。

## broker_reports

原始标准化回报表，message_id 唯一；`(broker, account_id, trading_day, broker_sequence)` 在 sequence 有效时唯一。记录 raw_payload_ref、received_at 和 processing_result，支持重新处理隔离消息。

## trades

主键内部 trade_key；唯一键 `(broker, account_id, trading_day, broker_trade_id)`。包含 order_id、instrument、side、quantity、price、commission、trade_time、recorded_at。成交入库与 TradeRecorded Outbox 同事务。

## ledger_entries

追加式双重记账：transaction_id 下借贷平衡；字段包含 account_id、ledger_account、currency、amount、direction、business_type、reference_type/id、effective_at、recorded_at、version。禁止直接改余额；余额是分录投影。每个 transaction_id 的同币种借贷合计必须为零。

## outbox / inbox

- outbox：message_id 唯一，aggregate_id/version、payload、created_at、published_at、attempt_count、next_attempt_at、last_error；按未发布状态和时间索引。
- inbox：`(consumer_name, message_id)` 唯一，received_at、processed_at、result；业务变更与 processed 标记同事务。
- Outbox 发布使用 claim/lease，Worker 崩溃后可回收；超过预算进入 dead-letter 并告警。

## snapshots

唯一键 `(aggregate_type, aggregate_id, aggregate_version)`；包含 schema_version、payload/ref、checksum、created_at。只加载 checksum 正确且版本不超过 Journal 最大版本的最新快照。

## reconciliation_cases

包含 case_id、type、severity、broker/local evidence、status、owner、proposed_action、approval、created/resolved_at。P0/P1 差异禁止静默自动关闭。

## 分区、索引和保留

- Journal、Broker report、Trade、Audit 优先按 trading_day/月分区；分区策略必须通过查询与恢复压测。
- 索引围绕活动订单、未发布 Outbox、交易日对账和 correlation_id；禁止无证据地给每列建索引。
- 热数据、审计保留和归档周期由合规/业务配置；归档前验证 checksum 和可恢复性。
- Schema 迁移采用 expand/migrate/contract，任何不可逆迁移先完成备份恢复演练。

## Redis Stream

每类 Stream 定义 maxlen/保留时长、consumer group、ACK 时点、pending 超时、claim 次数和 dead-letter。只有业务事务成功后 ACK；PEL reclaim 依赖 Inbox 幂等。trim 前必须确认永久事实已在 PostgreSQL，Redis 重建不得改变业务状态。
