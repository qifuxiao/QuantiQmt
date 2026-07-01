# INV-TRADING：交易不变量

1. MUST：策略只能产生 Target、OrderIntent 或 CancelIntent，不能调用 Broker。
2. MUST：每个 intent_id 最多对应一个 order_id。
3. MUST：订单先在 OMS 持久化注册，再执行 Risk；被拒订单同样可审计。
4. MUST：只有 OMS 能改变订单业务状态和累计成交数量。
5. MUST：只有持有效 fencing token 的 Trading Core Leader 能产生 Broker 副作用。
6. MUST：Submit/Cancel 超时属于 UNKNOWN_OUTCOME，禁止更换 ID 盲目重试。
7. MUST：任何外发订单都有已持久化 OrderRegistered 和 RiskPassed 证据。
8. MUST：Kill Switch、撤单和恢复控制拥有独立保留容量。
9. MUST NOT：策略停止或进程崩溃隐式改变活动订单状态。
10. MUST：订单、成交、人工修复和系统模式变化可通过 correlation_id 完整审计。
