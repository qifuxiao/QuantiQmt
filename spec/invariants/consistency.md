# INV-CONSISTENCY：一致性不变量

1. MUST：订单聚合更新与 Outbox 在同一 PostgreSQL 事务提交。
2. MUST：跨进程投递采用 At-Least-Once，Consumer 使用 Inbox/业务唯一键幂等。
3. MUST：Redis 是可重建加速层，不是订单、成交、账本或资金权威来源。
4. MUST：Broker 成交以 `(broker, account_id, trading_day, trade_id)` 唯一。
5. MUST：Ledger 只追加；每个 transaction_id 同币种借贷平衡。
6. MUST：0 ≤ order.cum_quantity ≤ order.quantity，累计成交单调不减。
7. MUST：快照包含 aggregate_version、schema_version 和 checksum；失败时从 Journal 重建。
8. MUST NOT：对账差异通过覆盖或删除历史事实修复；使用 Case 和调整事实。
9. MUST：恢复屏障打开前禁止新 OrderIntent。
10. MUST：Money/Price/Commission 最终判断和持久化不得使用二进制 float。
