> 本文规定通用工程风格。安全不变量和最新 Accepted ADR 保持最高优先级；事件、Payload、DTO、核心接口、Workflow 与状态机的规范性实现契约，以 `spec/manifest.yaml` 索引的 `spec/**` 为准。`docs/README.md` 仅提供解释性导航，不构成实现契约；docs 与 spec 冲突时按规范优先级裁决。本文历史示例不构成接口契约。

<!--
 * @Author: qifuxiao
 * @Date: 2026-07-01 11:48:42
 * @LastEditors: qifuxiao
 * @LastEditTime: 2026-07-01 11:48:48
 * @FilePath: /QuantiQmt/docs/standards/01-Coding-Convention/01-Engineering-Convention-Part03.md
 * @Description: 
 * 
 * Copyright (c) 2026 by qifuxiao <867225266@qq.com>, All Rights Reserved.
-->
# quantiqmt Engineering Convention

> Part03：Event Driven / OMS / Gateway Engineering Standard

---

# 21. Event Engineering Convention

## 21.1 Event First

quantiqmt 使用事件传播已经发生的跨组件事实，但不以 Event 代替所有调用。统一规则：

- Strategy 发送 `SubmitOrderIntent` Command，不能调用 Broker。
- Order Application 先命令 OMS 注册订单，再调用 Risk 获取确定性 Decision。
- OMS 根据 RiskDecision 推进状态，并产生 Domain/Integration Event。
- 同进程纯领域计算直接调用；需要明确结果的动作使用 Command；读取使用 Query。

唯一交易顺序为：

```text
OrderIntent → OMS Register → Risk Decision → OMS Transition → Execution → Broker
```

禁止用广播事件冒充需要明确接收者和结果的下单、撤单及控制命令。详细契约见 `docs/10-EventDriven/Message-Contracts.md`。

---

## 21.2 Event Classification

整个系统 Event 分为四类：

```
Domain Event

Application Event

Integration Event

Infrastructure Event
```

---

### Domain Event

描述：

领域变化。

例如：

```
OrderCreatedEvent

TradeExecutedEvent

PositionChangedEvent
```

---

### Application Event

描述：

业务流程。

例如：

```
StrategyStartedEvent

RiskCheckedEvent

OMSRecoveredEvent
```

---

### Integration Event

描述：

跨系统通信。

例如：

```
BrokerConnectedEvent

KafkaPublishedEvent

RedisExpiredEvent
```

---

### Infrastructure Event

描述：

基础设施。

例如：

```
DatabaseConnectedEvent

HeartbeatEvent

HealthCheckEvent
```

---

## 21.3 Event Naming

统一：

```
Verb + Event
```

例如：

```
OrderSubmittedEvent

TradeExecutedEvent

PositionChangedEvent
```

禁止：

```
OrderEvent1

TradeMsg

UpdateEvent
```

---

## 21.4 Event Metadata

所有 Event 必须包含：

```
event_id

event_type

aggregate_id

aggregate_type

timestamp

correlation_id

trace_id

version

source
```

以后：

Replay。

Tracing。

Audit。

全部依赖这些字段。

---

# 22. EventBus Convention

## 22.1 Single Event Bus

整个系统：

只有一个 EventBus。

禁止：

多个 EventBus。

---

## 22.2 Publish / Subscribe

统一：

```
publish()

subscribe()

unsubscribe()
```

禁止：

直接：

调用消费者。

---

## 22.3 Event Ordering

同一个 Aggregate：

事件：

必须：

保持顺序。

例如：

```
OrderCreated

↓

OrderSubmitted

↓

OrderAccepted

↓

TradeExecuted
```

不能：

乱序。

---

## 22.4 Event Immutability

Event：

发布以后：

不可修改。

禁止：

```
event.price=10
```

---

# 23. OMS Convention

## 23.1 Single OMS

整个系统：

只有一个 OMS。

所有订单：

统一管理。

---

## 23.2 Strategy

Strategy：

禁止：

```
buy()

sell()

cancel()
```

统一：

```
emit_signal()
```

---

## 23.3 Order Ownership

订单：

唯一拥有者：

OMS。

禁止：

```
Strategy

保存订单

Risk

保存订单
```

---

## 23.4 Order Lifecycle

统一：

```
NEW

↓

VALIDATED

↓

RISK_APPROVED

↓

CREATED

↓

SUBMITTED

↓

ACCEPTED

↓

PARTIAL

↓

FILLED
```

禁止：

跳状态。

---

# 24. Gateway Convention

## 24.1 Interface First

所有 Gateway：

必须：

先定义 Interface。

例如：

```
MarketGateway

ExecutionGateway

BrokerGateway

StorageGateway
```

之后：

再实现：

```
MiniQMTBrokerGateway

BacktestBrokerGateway
```

---

## 24.2 Domain Isolation

Domain：

禁止：

引用：

```
xtquant

redis

sqlalchemy

fastapi
```

只能：

引用：

Gateway。

---

## 24.3 Gateway Responsibility

Gateway：

负责：

```
协议转换

异常转换

连接管理

重试

超时

健康检查
```

禁止：

业务逻辑。

---

# 25. State Machine Convention

所有：

生命周期对象：

必须：

StateMachine。

包括：

```
Order

Strategy

Portfolio

Gateway

Connection
```

统一：

```
transition()
```

禁止：

```
status=
```

---

# 26. Application Convention

Application：

负责：

Workflow。

例如：

```
SubmitOrderWorkflow

RecoverWorkflow

StartupWorkflow
```

Application：

禁止：

业务规则。

业务规则：

属于：

Domain。

---

# 27. Command / Query Convention

采用：

CQRS。

Command：

修改状态。

例如：

```
SubmitOrderCommand

CancelOrderCommand
```

Query：

读取数据。

例如：

```
GetPositionQuery

GetAccountQuery
```

禁止：

Command：

返回：

复杂对象。

---

# 28. DTO Convention

DTO：

只能：

Application。

Interface。

使用。

禁止：

DTO：

进入：

Domain。

DTO：

统一：

```
xxxDTO
```

例如：

```
OrderDTO

PositionDTO

AccountDTO
```

---

# 29. Transaction Convention

一个事务：

只能：

修改：

一个 Aggregate。

跨 Aggregate：

统一：

Event。

禁止：

Application：

开启：

超大事务。

---

# 30. Concurrency Convention

禁止：

共享对象。

统一：

```
Queue

Event

Message
```

线程之间：

只能：

传递：

Immutable Object。

---

# 31. Dependency Convention

依赖：

必须：

单向。

```
Interfaces

↓

Application

↓

Domain

↓

Shared

Infrastructure

↓

Domain Interface
```

禁止：

循环依赖。

---

# 32. Code Review Checklist

每个 PR：

必须检查：

```
□ 是否符合 ADR？

□ 是否新增 Event？

□ Event 是否进入 Event Catalog？

□ 是否违反 DDD？

□ 是否绕过 OMS？

□ 是否绕过 Gateway？

□ 是否违反 StateMachine？

□ 是否新增测试？

□ 是否增加日志？

□ 是否增加 TraceID？
```

任何一项：

失败。

禁止：

Merge。

---

Part03 End
