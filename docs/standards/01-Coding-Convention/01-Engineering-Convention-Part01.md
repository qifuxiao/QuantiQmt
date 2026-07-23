# quantiqmt Engineering Convention

> **Authority notice：**本文规定通用编码风格；安全与交易不变量及最新 Accepted ADR 保持最高优先级。Event、Payload、DTO、核心接口、Workflow 和状态机的规范性实现契约，以 `spec/manifest.yaml` 索引的 `spec/**` 为准。`docs/README.md` 仅是解释性导航，不构成实现契约；本文及其他 `docs/**` 与 `spec/**` 冲突时，按仓库规范优先级处理。本文历史示例不构成接口契约。

> Version: 1.0
>
> Status: Accepted
>
> Last Updated: 2026-06-30
>
> Applicable Scope: Entire quantiqmt Project

---

# 1. Introduction

## 1.1 Purpose

本文档定义 quantiqmt 项目的统一工程开发规范（Engineering Convention）。

所有开发人员必须遵循本文档。

本规范用于保证：

- 架构一致性
- 编码一致性
- 长期可维护性
- 可测试性
- 可扩展性
- 高可读性
- 高可观测性

本文档属于项目最高工程规范。

所有代码 Review 必须遵守。

---

## 1.2 Relationship with ADR

Architecture Decision Record（ADR）负责定义：

> 为什么这样设计（Why）

Engineering Convention 负责定义：

> 如何实现（How）

关系如下：

```
Architecture

↓

ADR

↓

Engineering Convention

↓

Implementation

↓

Test

↓

Deployment
```

任何代码：

不得违反 ADR。

任何代码：

必须符合 Engineering Convention。

---

## 1.3 Design Philosophy

整个项目遵循以下原则：

### Architecture First

先设计架构。

再开发代码。

禁止：

先写代码。

后设计架构。

---

### Domain First

所有业务：

首先建立领域模型。

而不是数据库模型。

---

### Event First

跨 Context 协作必须采用公开且版本化的契约：Command 表达动作、Event 表达事实、Query 表达读取。同进程纯计算可以直接调用；禁止的是绕过 Application/Port 修改其他 Context 内部状态，而不是禁止所有函数调用。消息规范见 `docs/10-EventDriven/`。

---

### Interface First

所有外部依赖：

必须先定义 Interface。

再实现。

---

### State Machine First

所有生命周期对象：

必须建立状态机。

禁止：

直接修改状态。

---

### Test First

所有核心模块：

必须具有：

单元测试。

---

# 2. Coding Principles

整个项目遵循以下开发原则。

## 2.1 Single Responsibility Principle（SRP）

一个类：

只能负责一件事情。

例如：

正确：

```
OrderRepository

OrderService

OrderStateMachine
```

错误：

```
OrderManager

↓

负责：

订单

数据库

日志

风控

Broker
```

---

## 2.2 Open Closed Principle（OCP）

模块：

允许扩展。

禁止修改。

例如：

新增：

Broker：

```
MiniQMT

↓

CTP
```

不需要：

修改：

OMS。

---

## 2.3 Dependency Inversion Principle（DIP）

Domain：

只能依赖抽象。

禁止：

依赖：

MiniQMT。

Redis。

SQLAlchemy。

例如：

正确：

```
OrderRepository
```

错误：

```
SQLAlchemy Session
```

---

## 2.4 High Cohesion

同一个 Context：

所有代码：

放在一起。

例如：

Trading Context：

```
Order

Trade

Execution

OMS
```

不要：

跨目录。

---

## 2.5 Low Coupling

Context：

只能：

通过：

Event。

Interface。

通信。

禁止：

互相引用内部实现。

---

# 3. Naming Convention

命名必须统一。

整个项目禁止：

个人风格。

---

## 3.1 Package

全部：

snake_case

例如：

```
market

strategy

portfolio

risk

broker
```

禁止：

```
Market

Strategy

RiskEngine
```

---

## 3.2 Module

全部：

snake_case.py

例如：

```
order_service.py

order_repository.py

market_gateway.py
```

禁止：

```
OrderService.py

orderservice.py

Order_Service.py
```

---

## 3.3 Class

全部：

PascalCase

例如：

```
Order

OrderRepository

BrokerGateway

RiskRule
```

禁止：

```
order

orderService

broker_gateway
```

---

## 3.4 Function

全部：

snake_case

例如：

```
submit_order()

publish_event()

recover_orders()
```

禁止：

```
SubmitOrder()

DoSubmit()

sendOrder()
```

---

## 3.5 Variable

全部：

snake_case

例如：

```
order_id

strategy_id

risk_result
```

禁止：

```
OrderID

strategyID

RiskResult
```

---

## 3.6 Constant

全部：

UPPER_CASE

例如：

```
DEFAULT_TIMEOUT

MAX_RETRY

EVENT_VERSION
```

---

## 3.7 Event

统一：

```
xxxEvent
```

例如：

```
TickEvent

TradeEvent

SignalEvent

RiskRejectedEvent
```

---

## 3.8 Exception

统一：

```
xxxException
```

例如：

```
BrokerDisconnectedException

RiskRejectedException

OrderNotFoundException
```

---

## 3.9 Interface

Python：

不使用：

I 前缀。

正确：

```
BrokerGateway

OrderRepository

MarketGateway
```

错误：

```
IBroker

IRepository

IMarketGateway
```

---

# 4. Directory Convention

整个项目采用：

DDD + Bounded Context。

禁止：

按技术划分。

例如：

错误：

```
models/

services/

controllers/

dao/

utils/
```

正确：

```
domain/

market/

strategy/

trading/

portfolio/

risk/

account/
```

每个 Context：

保持独立。

---

## 4.1 Context Structure

每个 Context：

统一目录。

例如：

```
order/

├── entities/

├── events/

├── repositories/

├── services/

├── value_objects/

├── specifications/

└── state_machine/
```

禁止：

不同 Context：

不同风格。

---

# 5. Import Convention

Import：

必须按照以下顺序：

```
Python Standard Library

↓

Third Party

↓

quantiqmt
```

例如：

```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from quantiqmt.domain.order.entities import Order
```

---

禁止：

```
from xxx import *
```

禁止：

循环 Import。

禁止：

跨 Context 引用内部模块。

只能引用：

Public Interface。

---

# 6. Type Hint Convention

整个项目：

100%

Type Hint。

正确：

```python
def submit_order(
    order: Order,
) -> OrderResult:
    ...
```

错误：

```python
def submit(order):
    ...
```

禁止：

Any。

除非：

Framework：

必须。

---

# 7. Documentation Convention

所有：

Public API。

必须：

Docstring。

例如：

```python
class BrokerGateway:
    """
    Unified Broker Gateway Interface.

    Responsible for:
    - Submit Order
    - Cancel Order
    - Query Account
    - Query Position
    """
```

复杂算法：

必须：

增加：

设计说明。

禁止：

代码解释代码。

例如：

错误：

```
# add one

i += 1
```

正确：

```
# VWAP Algorithm

...
```

---

# 8. General Coding Rules

禁止：

超过：

3 层：

if。

建议：

Guard Clause。

例如：

错误：

```
if x:

    if y:

        if z:
```

正确：

```
if not x:
    return

if not y:
    return

if not z:
    return
```

---

禁止：

Magic Number。

必须：

Constant。

例如：

错误：

```
retry = 3
```

正确：

```
MAX_RETRY = 3
```

---

禁止：

Magic String。

必须：

Enum。

例如：

错误：

```
status = "filled"
```

正确：

```
OrderStatus.FILLED
```

---

Part01 End
