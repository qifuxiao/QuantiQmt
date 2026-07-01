# State Machine Catalog

> Status: Proposed  
> 业务代码不得直接赋值状态；必须通过有 Guard 的 transition，并生成状态变化事件。详细订单迁移表见 [OMS-And-Risk-Specification.md](OMS-And-Risk-Specification.md)。

## Order

```mermaid
stateDiagram-v2
    [*] --> REGISTERED
    REGISTERED --> RISK_PENDING
    RISK_PENDING --> REJECTED
    RISK_PENDING --> APPROVED
    APPROVED --> SUBMITTING
    SUBMITTING --> SUBMITTED
    SUBMITTING --> SUBMIT_UNKNOWN
    SUBMIT_UNKNOWN --> SUBMITTED
    SUBMIT_UNKNOWN --> FAILED
    SUBMIT_UNKNOWN --> SUSPENDED
    SUBMITTED --> PARTIALLY_FILLED
    SUBMITTED --> CANCEL_PENDING
    PARTIALLY_FILLED --> CANCEL_PENDING
    PARTIALLY_FILLED --> FILLED
    CANCEL_PENDING --> CANCEL_UNKNOWN
    CANCEL_PENDING --> CANCELED
    CANCEL_PENDING --> PARTIALLY_FILLED
    CANCEL_PENDING --> FILLED
    CANCEL_UNKNOWN --> CANCELED
    CANCEL_UNKNOWN --> PARTIALLY_FILLED
    CANCEL_UNKNOWN --> FILLED
    CANCEL_UNKNOWN --> SUSPENDED
```

## Position（净持仓账户）

```mermaid
stateDiagram-v2
    [*] --> FLAT
    FLAT --> LONG: buy trade
    FLAT --> SHORT: short sell trade
    LONG --> LONG: add/reduce, qty > 0
    LONG --> FLAT: sell, qty = 0
    LONG --> SHORT: crossing trade if market/account permits
    SHORT --> SHORT: add/reduce, qty < 0
    SHORT --> FLAT: cover, qty = 0
    SHORT --> LONG: crossing trade if permitted
```

Position 的权威数据是数量和账本事实，状态只是派生值。禁止单独持久化一个可能与 quantity 冲突的 status。对冲模式账户应使用独立 long/short lot 聚合，不套用净持仓跨零规则。

## Portfolio Projection

```mermaid
stateDiagram-v2
    [*] --> EMPTY
    EMPTY --> RECOVERING
    RECOVERING --> READY: snapshot + replay verified
    RECOVERING --> INCONSISTENT: checksum/difference
    READY --> STALE: event lag/freshness breach
    STALE --> READY: caught up + verified
    READY --> INCONSISTENT: reconciliation difference
    INCONSISTENT --> RECOVERING: repair approved
    READY --> CLOSED: trading day close checkpoint
    CLOSED --> RECOVERING: next session
```

只有 READY 投影可用于扩大风险敞口的风控决策。

## Account

```mermaid
stateDiagram-v2
    [*] --> DISCONNECTED
    DISCONNECTED --> SYNCING: broker connected
    SYNCING --> READY: account/position reconciled
    SYNCING --> INCONSISTENT: difference unsafe
    READY --> STALE: snapshot age exceeded
    READY --> RESTRICTED: risk/operations restriction
    STALE --> SYNCING: refresh
    INCONSISTENT --> SYNCING: repair approved
    RESTRICTED --> SYNCING: restriction removed
    READY --> DISCONNECTED: broker lost
```

## Broker Connection

```mermaid
stateDiagram-v2
    [*] --> DISCONNECTED
    DISCONNECTED --> CONNECTING
    CONNECTING --> CONNECTED
    CONNECTING --> BACKOFF: failure
    BACKOFF --> CONNECTING: retry budget remains
    BACKOFF --> FAILED: budget exhausted
    CONNECTED --> DEGRADED: heartbeat/query failure
    DEGRADED --> CONNECTED: healthy window
    DEGRADED --> DISCONNECTED: connection lost
    CONNECTED --> DISCONNECTING: requested stop
    DISCONNECTING --> DISCONNECTED
    FAILED --> CONNECTING: operator/recovery policy
```

## Gateway Lifecycle

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> STARTING
    STARTING --> READY
    STARTING --> FAILED
    READY --> DEGRADED
    DEGRADED --> READY
    DEGRADED --> FAILED
    READY --> STOPPING
    DEGRADED --> STOPPING
    FAILED --> STOPPING
    STOPPING --> STOPPED
```

Connection 是外部会话状态，Gateway 是组件生命周期；两者不能混成一个枚举。

## Strategy

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> INITIALIZING
    INITIALIZING --> READY: checkpoint/data valid
    INITIALIZING --> ERROR
    READY --> RUNNING: session + operator enable
    RUNNING --> PAUSED: manual/risk/data stale
    PAUSED --> RUNNING: prerequisites + approval
    RUNNING --> STOPPING
    PAUSED --> STOPPING
    ERROR --> STOPPING
    STOPPING --> STOPPED
```

暂停策略不取消其已有订单所有权；OMS 继续管理活动订单。恢复 RUNNING 前检查行情、账户、组合和配置版本。

## System Trading Mode

```mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> NORMAL: recovery barrier passed
    STARTING --> SAFE: partial availability
    NORMAL --> DEGRADED: noncritical dependency/lag
    DEGRADED --> NORMAL: healthy window + policy
    NORMAL --> SAFE: trading safety uncertain
    DEGRADED --> SAFE
    SAFE --> HALTED: severe inconsistency/manual halt
    SAFE --> DEGRADED: repair + approval
    HALTED --> SAFE: dual approval + recovery
```

NORMAL 允许策略新单；DEGRADED 按范围限制；SAFE 禁止扩大风险但保留查询、撤单和经规则批准的减仓；HALTED 仅允许恢复控制命令。

## Reconciliation Case

```mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> INVESTIGATING
    INVESTIGATING --> PROPOSED
    PROPOSED --> APPROVED
    PROPOSED --> REJECTED
    APPROVED --> APPLYING
    APPLYING --> RESOLVED
    APPLYING --> FAILED
    FAILED --> INVESTIGATING
    RESOLVED --> [*]
```

每次迁移记录 operator、reason、evidence、approval 和版本。P0/P1 case 不能自动从 OPEN 直接 RESOLVED。
