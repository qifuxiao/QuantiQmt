# OMS 与风控详细规格

> Status: Proposed

## 不变量

1. 每个 intent_id 最多创建一个 order_id。
2. 只有 OMS 能改变订单状态和累计成交量。
3. 未持久化 `APPROVED` 事实前不能产生 Broker Submit Command。
4. `cum_quantity` 单调不减且不得大于 quantity。
5. `(broker, account, trading_day, trade_id)` 只记账一次。
6. 任何不确定结果不得被映射为 FAILED 后自动重下。
7. 非 Leader 或 fencing token 过期实例不能产生外部副作用。

## 完整订单状态

| 状态 | 含义 | 是否终态 |
|---|---|---|
| REGISTERED | 意图已持久化 | 否 |
| RISK_PENDING | 等待风险决策 | 否 |
| REJECTED | 风控或 Broker 明确拒绝 | 是 |
| APPROVED | 已批准但未发送 | 否 |
| SUBMITTING | 已创建发送尝试 | 否 |
| SUBMIT_UNKNOWN | 请求结果不确定 | 否 |
| SUBMITTED | Broker 已确认活动订单 | 否 |
| PARTIALLY_FILLED | 部分成交 | 否 |
| CANCEL_PENDING | 已请求撤单，结果未定 | 否 |
| CANCEL_UNKNOWN | 撤单结果不确定 | 否 |
| CANCELED | 明确撤销，可能有部分成交 | 是 |
| FILLED | 完全成交 | 是 |
| EXPIRED | Broker 明确过期 | 是 |
| FAILED | 确认未创建外部订单的技术失败 | 是 |
| SUSPENDED | 等待人工/对账处理 | 否 |

## 迁移表

| 当前状态 | 输入 | Guard | 新状态 | 事件/动作 |
|---|---|---|---|---|
| REGISTERED | StartRisk | 快照可用 | RISK_PENDING | EvaluateRisk |
| RISK_PENDING | RiskPass | 版本匹配 | APPROVED | OrderApproved |
| RISK_PENDING | RiskReject | 版本匹配 | REJECTED | OrderRejected |
| APPROVED | Dispatch | Leader 且未触发 Kill Switch | SUBMITTING | SubmitOrder |
| SUBMITTING | BrokerAck/活动回报 | ID 可关联 | SUBMITTED | OrderSubmitted |
| SUBMITTING | 明确 Broker 拒绝 | 证据确定 | REJECTED | OrderRejected |
| SUBMITTING | 超时/断连 | 结果不可知 | SUBMIT_UNKNOWN | QueryBroker |
| SUBMIT_UNKNOWN | ReconcileFound | 唯一映射 | SUBMITTED/部分成交/终态 | ImportReports |
| SUBMIT_UNKNOWN | ReconcileAbsent | 超过可见性窗口且证据确定 | FAILED | SubmitFailed |
| SUBMIT_UNKNOWN | 冲突/证据不足 | - | SUSPENDED | P1 + 人工工单 |
| SUBMITTED | TradeReport | 成交唯一且 cum < qty | PARTIALLY_FILLED | TradeRecorded |
| SUBMITTED/PARTIALLY_FILLED | TradeReport | cum = qty | FILLED | TradeRecorded |
| SUBMITTED/PARTIALLY_FILLED | CancelRequest | 未终态 | CANCEL_PENDING | CancelOrder |
| CANCEL_PENDING | CancelAck | leaves 已撤 | CANCELED | OrderCanceled |
| CANCEL_PENDING | TradeReport | 仍可成交 | CANCEL_PENDING/FILLED | TradeRecorded |
| CANCEL_PENDING | 超时 | 结果不可知 | CANCEL_UNKNOWN | QueryBroker |
| CANCEL_UNKNOWN | Reconcile | 按 Broker 事实 | 活动/成交/CANCELED/SUSPENDED | Reconciled |

终态收到迟到成交时不能简单拒绝：若 Broker 证明成交有效，记录成交并迁移至与累计成交一致的状态，同时产生严重差异事件。非法迁移必须隔离消息并告警，不允许静默跳过。

## 回报乱序归并

### 事实身份与幂等

- Broker OrderReport 必须携带 `(broker, account_id, trading_day, report_id)`；Broker Trade 必须携带 `(broker, account_id, trading_day, trade_id)`。缺少业务唯一键的事实不得进入 Order 聚合。
- 相同 identity、相同内容是幂等 no-op，不改变状态、累计成交量或 aggregate version；相同 identity、不同内容进入 `SUSPENDED` 并开启对账 Case。
- canonical fingerprint 只包含 Broker 业务事实。Trade 排除本地 `received_at` 及内部补充的 order/client 映射；OrderReport 排除 `received_at` 与内部 order_id。字段集合以 `SM-ORDER.fact_identity.canonical_fingerprint` 为准，因此重复回调仅接收时间不同仍是 no-op。
- 迟到且不增加信息的非回退报告是 no-op。任何报告不得降低 `cum_quantity`；超量或回退统一以 `QQ-OMS-5002` 在修改状态/version 前拒绝。
- 非成交事件禁止携带或修改累计成交量。每个被接受的新事实只推进一次 aggregate version；初始 version 为 1，恢复 version 必须等于最后已提交聚合事件版本且不小于 1。

### 撤单竞态

- `PARTIALLY_FILLED` 可以接收后续 `PartialTrade` 并保持原状态。
- `CANCEL_PENDING` 与 `CANCEL_UNKNOWN` 收到部分成交时必须记账并保持撤单状态；收到全量成交时进入 `FILLED`。
- 撤单请求被明确拒绝时，原订单仍活动：trade-derived cum 为零回到 `SUBMITTED`，介于零和总量之间回到 `PARTIALLY_FILLED`。若 Broker 在已进入合法撤单历史后声称原始下单被拒绝，这是历史矛盾，必须 `SUSPENDED`。
- 全量成交后的迟到撤单确认是 stale no-op，不能把 `FILLED` 改为 `CANCELED`。UNKNOWN 只触发查询/对账，绝不自动重新提交或重新撤单。

### Guard 输入事实

Guard 不是默认通过的布尔开关。Application 必须提供具名事实：快照 identity/quality、expected order version、leader/fencing/mode、Broker 唯一关联、结果确定性、可见窗口证据及数量关系。缺失事实等同 Guard 失败；Domain 不自行访问 DB、Broker 或系统时钟补齐事实。

Guard 失败必须遵守规范表：版本冲突返回 `QQ-COMMON-1003`，快照不可用返回 `QQ-RISK-4002`，数量/矛盾状态返回 `QQ-OMS-5002`；歧义映射和同 identity 内容冲突进入 `SUSPENDED` 并开 Case；可见窗口未满足是保持 UNKNOWN 的 no-op。除显式冲突迁移外，失败前后 state、cum、processed identities 和 aggregate version 原子不变。

### 累计成交权威算法

Order 的 `cum_quantity` 只等于所有已接受且唯一的 Broker Trade identity 的单笔 `quantity` 之和。Broker OrderReport 的 `cum_quantity` 仅用于对账，不直接覆盖聚合值；不一致时进入 `SUSPENDED`。恢复必须加载 identity、canonical content fingerprint、可用 Broker sequence 和 provisional client/broker mapping，否则恢复屏障不得打开。

每个 PartialTrade/FullTrade Guard 使用 `candidate_cumulative = stored trade-derived cumulative + 当前 unseen unique Trade.quantity`，不能要求 Trade payload 提供不存在的累计字段。异常事件和所有 reconciliation import 事件同样必须持久化来源 report/trade identity 与 fingerprint，重复重放为不推进 version 的 no-op。

## Spec 0.3 兼容、迁移与回滚

- 本次只增加 Order 迁移与归并约束，不改变既有消息字段；属于行为收紧。旧实现不得在新规范下继续写入 Order Journal。
- 升级前暂停新 OrderIntent，完成 Inbox/Journal drain，构建 processed fact identity+fingerprint 索引并校验 trade-derived cumulative quantity，再部署新 Domain 实现并执行恢复对账。
- Consumer/OMS 先升级，Execution/Broker producer 无需改消息版本。发现历史 identity 冲突或累计量差异时保持 SAFE/SUSPENDED，不自动修复历史。
- 回滚前再次关闭恢复屏障并停止新交易；若新迁移已写入 Journal，只能回滚到支持 Spec 0.3 的实现，禁止旧状态机读取新事件后继续交易。

- 优先使用 Broker sequence；缺失时使用业务不变量和累计成交量，不仅依赖时间戳。
- 成交可先于委托确认：先建立 provisional mapping，随后补齐 broker_order_id；无法唯一关联则进入隔离队列。
- 状态回报不得降低 cum_quantity 或从终态回退到活动态。
- 重复成交由数据库唯一约束和 Inbox 双重防护。

## 风控规则矩阵

| 层级 | 典型规则 | 数据新鲜度 | 超时策略 |
|---|---|---|---|
| 系统 | Kill Switch、交易状态、依赖健康 | 实时 | fail-closed |
| 账户 | 可用资金、持仓、保证金、日损 | ≤ 配置阈值 | fail-closed |
| 组合 | 集中度、行业/因子暴露、杠杆 | ≤ 配置阈值 | fail-closed |
| 策略 | 单笔、累计仓位、频率、撤单率 | 实时 | fail-closed |
| 标的 | 白名单、价格偏离、涨跌停、停牌 | 行情阈值内 | fail-closed |
| 监控 | 异常统计、提示型规则 | 可配置 | 可 fail-open 并告警 |

具体新鲜度阈值属于版本化配置，默认不写死在代码。资金/持仓快照质量不是 FRESH 时，涉及开仓或扩大风险敞口的命令一律拒绝；减仓是否允许由独立规则明确判定。

## 风控确定性

RiskDecision 必须由 `{order snapshot, market/account/portfolio snapshot versions, rule_set_version}` 唯一决定。规则无数据库写入、网络调用和系统时钟读取；所需数据在调用前形成不可变快照。

## 人工修复

允许的修复命令包括 LinkBrokerOrder、ImportTrade、MarkConfirmedAbsent、ApplyLedgerAdjustment。每次修复需要操作者、原因、证据、审批策略、前后版本和审计事件；禁止直接 SQL 修改订单状态。

## 验收属性

- 任意消息重复 N 次，最终业务状态不变。
- 任意合法回报乱序，最终累计成交和终态一致。
- 任意时刻最多一个有效 SubmitOrder 外部副作用。
- 进程在每个持久化边界崩溃后重启，订单不会丢失或自动重复发送。
- 所有拒绝、超时、修复和模式切换均可从审计链解释。
