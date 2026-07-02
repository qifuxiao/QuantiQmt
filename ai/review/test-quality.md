# Test Quality Review

- [ ] 测试验证行为和不变量，不锁死内部实现。
- [ ] 包含边界、重复、乱序、超时、崩溃和恢复。
- [ ] 未用 sleep、随机时序或无限重试掩盖竞态。
- [ ] Clock、随机数、Broker 和数据版本可控制。
- [ ] Contract fixtures 与 spec Schema 一致。
- [ ] 关键状态迁移分支完整覆盖。
- [ ] 测试失败时信息足以定位 order/message/correlation。
- [ ] 没有跳过安全测试或放宽断言。
