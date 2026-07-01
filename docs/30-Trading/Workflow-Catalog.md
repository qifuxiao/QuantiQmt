# Workflow Catalog

> Status: Proposed  
> 本文定义核心流程的唯一顺序。每个步骤必须记录 correlation_id；省略的日志、指标和 Outbox 不代表可以省略实现。

## 系统启动与 Ready

```mermaid
sequenceDiagram
    participant S as Supervisor
    participant C as Config
    participant D as PostgreSQL/Redis
    participant O as OMS
    participant B as BrokerGateway
    participant R as Reconciliation
    participant M as MarketGateway
    participant T as StrategyRuntime
    S->>C: Load and validate versioned config
    S->>D: Connect and verify schema/stream
    S->>O: Acquire lease + fencing token
    O->>O: Restore snapshot + journal
    S->>B: Connect
    B-->>S: Session and capabilities
    S->>R: Reconcile orders/trades/account/positions
    R-->>S: Clean / Repairable / Unsafe
    alt clean or approved repair complete
        S->>M: Start and subscribe
        M-->>S: Market healthy window
        S->>T: Restore checkpoint and start
        S->>O: Transition READY
    else unsafe
        S->>O: SAFE or HALTED
    end
```

任何依赖失败都不能跳过恢复屏障。重试受总预算限制；预算耗尽保持进程可诊断并进入 DEGRADED/SAFE，而不是退出重启风暴。

## Submit Order

```mermaid
sequenceDiagram
    participant S as Strategy
    participant A as OrderApplication
    participant O as OMS
    participant R as Risk
    participant E as Execution
    participant B as Broker
    S->>A: SubmitOrderIntent(intent_id)
    A->>O: RegisterIntent
    O->>O: Persist OrderRegistered + Outbox
    O-->>A: order_id/version
    A->>R: Evaluate immutable snapshots
    R-->>A: RiskDecision
    A->>O: ApplyRiskDecision(expected_version)
    alt rejected
        O->>O: Persist REJECTED
        O-->>S: OrderRejected
    else approved
        O->>O: Persist APPROVED
        O->>E: SubmitOrderCommand
        E->>E: Persist attempt
        E->>B: submit(idempotency_key,fencing)
        alt definite response
            B-->>E: receipt/report
            E->>O: BrokerReport
            O->>O: Persist new state
        else timeout/connection lost after write
            E->>O: OutcomeUnknown
            O->>O: Persist SUBMIT_UNKNOWN
            O->>B: Query by client_order_id
        end
    end
```

步骤超时：注册 DB 超时不外发；Risk 超时 fail-closed；Broker 超时进入 UNKNOWN；事件发布失败由 Outbox 重试，不回滚已经提交的业务事实。

## Cancel Order

```mermaid
sequenceDiagram
    participant U as Strategy/Operator
    participant A as OrderApplication
    participant O as OMS
    participant E as Execution
    participant B as Broker
    U->>A: CancelOrder(cancel_request_id)
    A->>O: RequestCancel
    alt local cancellable before submit
        O->>O: Persist CANCELED
    else external active
        O->>O: Persist CANCEL_PENDING
        O->>E: CancelOrderCommand
        E->>B: cancel(idempotency_key,fencing)
        alt definite report
            B-->>O: Cancel/Trade report
            O->>O: Merge report and persist
        else unknown
            O->>O: Persist CANCEL_UNKNOWN
            O->>B: Query order
        end
    end
```

撤单期间仍可能成交，TradeReport 优先作为事实处理。重复 cancel_request_id 返回同一结果。

## Trade and Accounting

```mermaid
sequenceDiagram
    participant B as BrokerAdapter
    participant O as OMS
    participant DB as PostgreSQL
    participant L as AccountLedger
    participant P as PortfolioProjection
    participant R as RiskSnapshot
    B->>O: TradeReport
    O->>DB: Deduplicate + update Order + Outbox
    DB-->>O: committed
    O-->>L: TradeRecorded
    L->>DB: Balanced ledger transaction + Outbox
    L-->>P: LedgerTradePosted
    P->>P: Update position/PnL projection
    P-->>R: PositionChanged
```

任何下游失败由各自 Inbox 重放，不允许回滚 Broker 已发生的成交。Ledger 不平衡时消息进入隔离队列并触发 P0。

## Broker Disconnect and Reconnect

```mermaid
sequenceDiagram
    participant H as HealthService
    participant C as TradingCore
    participant B as BrokerGateway
    participant R as Reconciliation
    H->>C: Connection UNHEALTHY
    C->>C: Enter SAFE (no new risk)
    loop bounded exponential backoff
        C->>B: reconnect
    end
    B-->>C: connected
    C->>R: Query orders/trades/account/positions
    R-->>C: reconciliation result
    alt clean + healthy window
        C->>C: Operator/policy approves NORMAL
    else difference
        C->>C: remain SAFE/HALTED
    end
```

重连成功不自动恢复交易；必须完成对账、健康窗口和恢复审批。

## 配置热更新

```mermaid
sequenceDiagram
    participant O as Operator
    participant C as ConfigService
    participant X as Components
    O->>C: Propose version
    C->>X: Prepare(candidate)
    X-->>C: Valid/Invalid
    alt all required components valid
        C->>C: Activate atomically
        C-->>X: ConfigVersionActivated
        X->>X: Swap immutable snapshot at safe point
    else invalid/timeout
        C-->>O: Reject proposal
    end
```

## 通用失败策略

| 失败类型 | Retry | 状态 | 恢复 |
|---|---|---|---|
| 参数/业务拒绝 | No | 明确终态/保持原态 | 修正新请求 |
| 乐观锁冲突 | 重新读取后有限重试 | 不丢失原状态 | 单写者重新编排 |
| 幂等 I/O 短暂失败 | 有预算退避 | DEGRADED | 健康探测 |
| Broker 外部动作结果未知 | 禁止盲重试 | UNKNOWN | Query + Reconcile |
| 持久化不可用 | 不接受新风险动作 | SAFE | 验证写入和 Outbox |
| 数据差异/非法迁移 | No | SUSPENDED/HALTED | 工单与审计修复 |
