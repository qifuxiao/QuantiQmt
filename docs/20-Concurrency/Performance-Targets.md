# Performance Targets

> Status: Proposed  
> 本文给出服务目标；[Capacity-And-Performance.md](Capacity-And-Performance.md) 定义负载档位和测试方法。

在 Target 负载、系统内部且不含 MiniQMT/Broker/交易所外部耗时时：

| 路径 | P95 | P99 | 超限行为 |
|---|---:|---:|---|
| QMT callback copy→ingress queue | 0.5 ms | 1 ms | 标记回调拥塞 |
| Market normalize→published | 2 ms | 3 ms | 合并允许的快照/背压 |
| Strategy ordinary evaluation | 5 ms | 8 ms | 暂停慢策略，不阻塞其他策略 |
| Risk evaluation | 2 ms | 4 ms | 超时 fail-closed |
| OMS command excluding DB outage | 2 ms | 4 ms | 队列背压 |
| Approved→Broker call start | 2 ms | 3 ms | P1 when sustained |
| Internal MarketEvent→Broker call start | 15 ms | 20 ms | 降载/容量调查 |
| Trade received→Order committed | 5 ms | 10 ms | 不丢消息，积压告警 |
| Trade committed→Ledger/Position visible | 20 ms | 50 ms | Risk 使用 freshness gate |
| Kill Switch received→new intent blocked | 20 ms | 50 ms | 超限 P0 |

外部指标单独报告：Broker submit API latency、订单确认、首成交和撤单确认，不能混入内部 SLO 掩盖系统开销。

## 恢复目标

| 场景 | 初始目标 |
|---|---:|
| Strategy Worker 恢复 | 30 s |
| Projection 从有效快照恢复 | 60 s |
| QMT 重连后对账 | 60 s（受接口限制） |
| OMS 重启并完成恢复屏障 | 60 s（额定活动订单量） |
| Redis 全量重建 | 5 min |
| PostgreSQL 灾备 | 以演练结果确定，未演练不承诺 |

## 解释规则

- SLO 只有在明确硬件、Python/QMT 版本和负载档位下有效。
- 平均延迟不能替代 percentile；丢弃慢请求不能制造“达标”。
- 性能优化不得破坏审计、幂等、状态机或风控；无法同时满足时优先正确和安全。
