# Testing Standard

> Status: Proposed

## 层级与覆盖责任

| 层级 | 主要模块 | 外部依赖 | 必须验证 |
|---|---|---|---|
| Unit | Domain、状态机、Risk、Ledger | 全无 | 边界值、不变量、错误码 |
| Property/Model | OMS、Position、Ledger | 内存模型 | 重复、乱序、任意迁移序列、守恒 |
| Contract | Gateway、Repository、Bus、Clock | Fake + 真实服务 | API、错误、超时、幂等、版本 |
| Integration | Application、Outbox/Inbox、DB/Redis | 容器/测试实例 | 事务、ACK、重启、迁移 |
| Replay | Projection、Strategy、Recovery | 固定事件集 | 确定性、checksum、兼容版本 |
| Backtest | Strategy/Risk/Simulator | 历史数据 | 无未来函数、费用/滑点、可重复 |
| Simulation | 全交易链 | Broker Simulator | 部分成交、拒单、乱序、未知结果 |
| Paper | Live Adapter | QMT 模拟/实盘行情 | 交易日全流程、运维和告警 |
| Limited Live | 全系统 | 低限额真实账户 | 真实回报、对账、Kill Switch |

## 模块最低测试集

- MarketGateway：重复 Tick、gap、乱序、订阅幂等、断线重订、陈旧检测。
- Strategy：checkpoint、暂停恢复、无未来数据、相同输入确定输出。
- Risk：每条规则 pass/reject/boundary、stale snapshot、配置版本切换、超时 fail-closed。
- OMS：迁移表全边、重复 Command、版本冲突、迟到回报、终态成交修正。
- Execution/Broker：能力矩阵、限流、断连、submit/cancel UNKNOWN、fencing。
- Portfolio/Ledger：成交去重、跨零、费用、借贷平衡、重放一致。
- Recovery：每个持久化边界 kill、快照损坏、Broker 差异、Redis 丢失、PITR。
- Observability：Trace 完整、敏感数据脱敏、告警触发与恢复、Runbook 链接。

## 测试数据

Fixture 必须版本化并记录来源/checksum。生产数据使用前脱敏；禁止把真实凭证和完整账户信息进入测试仓库。时间、随机数、Broker 行为均可控制。

## Flaky Test

禁止通过无限重试掩盖不稳定测试。Flaky 测试必须隔离、登记 owner/issue/deadline；涉及订单一致性、安全和账本的测试不得被标记为可忽略。

## 完成定义

功能只有在代码、类型、迁移、日志/指标、单元/契约/故障测试、文档和 Runbook 同时完成后才算 Done。详细生产门禁见 [Test-And-Production-Acceptance.md](Test-And-Production-Acceptance.md)。
