# 测试、故障演练与生产准入

> Status: Proposed

## 测试金字塔

| 层级 | 必测内容 |
|---|---|
| Unit | 值对象、状态机、风险规则、费用与账本 |
| Property | 消息重复/乱序、金额守恒、状态不变量 |
| Contract | QMT/Redis/PostgreSQL/Clock/Simulator Adapter |
| Integration | Outbox/Inbox、事务、重启恢复、对账 |
| End-to-End | 行情→策略→风控→OMS→Broker→成交→账本 |
| Performance | 延迟、吞吐、背压、长稳、恢复追赶 |
| Chaos | 断连、超时、进程崩溃、磁盘满、网络分区 |

## 必须成立的属性

- 策略进程不具备 Broker Submit 能力。
- 所有外发订单存在已持久化 OrderRegistered 和 RiskPassed 证据。
- 同一 intent/idempotency_key 重复提交不会产生第二笔外部订单。
- 成交重复、乱序或先于委托回报时，最终账本和持仓仍正确。
- 任意持久化边界前后杀进程，恢复后不丢订单且不盲目重发。
- 账本每个 transaction_id 借贷平衡，投影可从 Journal 重建。
- Kill Switch 在队列高水位和依赖故障时仍拥有保留执行能力。

## 故障注入矩阵

| 注入点 | 时机 | 期望 |
|---|---|---|
| Trading Core kill | OrderRegistered 后 | 重启继续风控，不重复注册 |
| Trading Core kill | Broker 请求前/后 | 前者可安全发送；后者进入 UNKNOWN 并查询 |
| Redis disconnect | 消息发布期间 | Outbox 保留，恢复后重复投递但业务幂等 |
| PostgreSQL timeout | 订单注册期间 | 不外发订单，拒绝新意图 |
| Broker timeout | Submit/Cancel | UNKNOWN，不盲目重试 |
| Broker duplicate | Order/Trade report | 状态和账本只推进一次 |
| Broker reorder | Trade 先于 Order ack | provisional mapping/隔离后正确归并 |
| 双 Leader | 网络分区 | 旧 fencing token 被 Adapter 拒绝 |
| 行情 stale/corrupt | 策略运行中 | 标记质量、暂停或风控拒绝 |
| 磁盘满 | 审计写入 | 进入 SAFE，不静默丢审计 |

## 回放与一致性测试

- 相同 fixture、配置、Clock、随机种子重复回放，输出 checksum 一致。
- Live Adapter 和 Simulator 通过相同 OMS/Execution 契约用例。
- 从空库重建与从最新快照恢复的最终投影 checksum 一致。
- 每个支持的旧消息版本都有升级兼容 fixture。

## CI 门禁

- 格式、lint、严格类型检查、依赖漏洞和 secret 扫描通过。
- Unit/Property/Contract 测试通过，覆盖率只是辅助指标，核心状态迁移必须 100% 分支覆盖。
- 数据库迁移执行升级、回滚或前向修复测试。
- Mermaid/Markdown 链接和消息 schema 兼容检查通过。

## 阶段准入

### Paper Trading

所有核心契约、恢复和故障测试通过；连续 5 个交易日无无法解释的订单/成交差异；交易链可完整查询。

### 限额实盘

完成安全评审、灾备恢复、Kill Switch 演练和 Runbook 值守；使用独立低限额账户，逐日人工对账，不允许自动扩大额度。

### 正式生产

- 连续 20 个交易日 Paper/限额实盘达到 SLO。
- 24 小时 Target 长稳与 Stress 测试通过。
- 订单、成交、账本和 Broker 对账零未处置 P0/P1 差异。
- 备份 PITR、OMS 接管、QMT 重连和人工修复完成演练。
- 监控、告警、值班、升级、回滚及联系人 Runbook 已评审。
- 所有核心文档状态从 Proposed 变更为 Accepted，并记录批准人和版本。

## 上线否决条件

存在 UNKNOWN 订单无处置机制、双 Leader 无 fencing、审计可丢、策略可绕过风控、恢复依赖 Redis 缓存、无法执行 Kill Switch、没有 Broker 对账或没有明确回滚方案时，禁止实盘上线。
