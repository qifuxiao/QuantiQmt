# 系统架构

> Status: Proposed

## 整体架构图

```mermaid
flowchart LR
    subgraph External[外部系统]
        EX[交易所/行情源]
        QMT[MiniQMT]
        OPS[运维与交易控制台]
    end
    subgraph Edge[接入层]
        MG[Market Gateway]
        BG[Broker Adapter]
        API[Control API]
    end
    subgraph Core[交易核心]
        SE[Strategy Runtime]
        ORCH[Order Application Service]
        RE[Risk Engine]
        OMS[OMS Leader]
        EE[Execution Engine]
        PA[Portfolio/Account Projection]
        RC[Reconciliation]
    end
    subgraph Backbone[消息与数据]
        BUS[Durable Stream]
        PG[(PostgreSQL: Journal/Ledger)]
        REDIS[(Redis: Stream/Cache/Lease)]
    end
    subgraph Ops[平台能力]
        OBS[Logs/Metrics/Tracing/Alert]
        CFG[Config/Secrets]
    end

    EX --> QMT --> MG --> BUS --> SE
    SE -->|OrderIntent command| ORCH --> RE
    RE -->|RiskDecision| ORCH --> OMS --> EE --> BG --> QMT
    QMT --> BG -->|Order/Trade report| OMS
    OMS -->|domain events| BUS
    BUS --> PA
    BUS --> PG
    QMT <--> RC
    RC <--> PG
    RC --> OMS
    OPS --> API --> ORCH
    Core -. telemetry .-> OBS
    Edge -. telemetry .-> OBS
    CFG --> Edge
    CFG --> Core
```

## 唯一交易链路

```mermaid
sequenceDiagram
    participant M as Market Gateway
    participant S as Strategy
    participant A as Order Application
    participant R as Risk
    participant O as OMS
    participant E as Execution
    participant B as Broker
    M-->>S: MarketEvent
    S->>A: SubmitOrderIntent
    A->>O: RegisterIntent
    O-->>A: OrderRegistered
    A->>R: Evaluate(order snapshot)
    R-->>A: RiskDecision
    A->>O: Approve or Reject
    O->>E: SubmitOrder command
    E->>B: broker request(idempotency_key)
    B-->>E: acknowledgement/report
    E->>O: BrokerReport command
    O-->>S: OrderEvent
```

先注册意图再风控，确保被拒订单同样可审计。只有 OMS 可以推进订单状态；Risk 不修改订单，Execution 不解释业务状态。

## 部署单元

- Market Process：QMT 行情回调、标准化、去重、时间戳和发布。
- Strategy Worker：按策略或策略组隔离计算；崩溃不影响交易核心。
- Trading Core：Order Application、Risk、OMS Leader、Execution；优先保证确定性。
- Broker Process：隔离 MiniQMT SDK 故障和回调线程。
- Projection/Storage Worker：持久化、账户持仓投影、报表。
- Control/Observability：控制面、指标、告警，不参与下单数据面。

Redis/Stream 故障时不能切换到“绕过消息系统直接下单”。交易核心根据故障矩阵进入 Degraded 或 Safe Mode。
