# Trading Safety Review

- [ ] 策略没有 Broker/DB/Redis/OMS Repository 能力。
- [ ] OMS 注册和批准事实均在 Broker 副作用之前持久化。
- [ ] Submit/Cancel UNKNOWN 没有盲目重试。
- [ ] 幂等键在重试中稳定，fencing token 被验证。
- [ ] 重复/乱序/迟到回报保持订单不变量。
- [ ] Risk stale/partial/timeout fail-closed。
- [ ] Kill Switch 和撤单保留容量。
- [ ] Money/Price/Commission 不使用 float。
- [ ] Ledger 平衡且差异不覆盖历史。
- [ ] 恢复屏障前禁止新单。
