> **Authority notice：**本文规定通用领域建模风格；安全与交易不变量及最新 Accepted ADR 保持最高优先级。Event、Payload、DTO、核心接口、Workflow 和状态机的规范性实现契约，以 `spec/manifest.yaml` 索引的 `spec/**` 为准。`docs/README.md` 仅是解释性导航，不构成实现契约；本文及其他 `docs/**` 与 `spec/**` 冲突时，按仓库规范优先级处理。本文历史示例不构成接口契约。

<!--
 * @Author: qifuxiao
 * @Date: 2026-07-01 11:46:28
 * @LastEditors: qifuxiao
 * @LastEditTime: 2026-07-01 11:46:34
 * @FilePath: /QuantiQmt/docs/standards/01-Coding-Convention/01-Engineering-Convention-Part02.md
 * @Description: 
 * 
 * Copyright (c) 2026 by qifuxiao <867225266@qq.com>, All Rights Reserved.
-->
# quantiqmt Engineering Convention

> Part02：Domain-Driven Design Engineering Standard

---

# 9. Domain Model Convention

## 9.1 Domain First

整个系统首先建立领域模型（Domain Model）。

禁止：

```
Database First
```

例如：

错误：

```
Table

↓

Entity

↓

Business
```

正确：

```
Business

↓

Domain

↓

Repository

↓

Database
```

数据库只是持久化。

不是业务模型。

---

## 9.2 Rich Domain Model

整个项目采用：

Rich Domain Model。

禁止：

Anemic Domain Model。

错误：

```
Order

只有：

id

price

volume

getter

setter
```

正确：

```
Order

↓

create()

submit()

cancel()

fill()

reject()

transition()
```

Entity：

负责：

业务行为。

不是：

DTO。

---

## 9.3 Domain Purity

Domain：

禁止引用：

- SQLAlchemy
- Redis
- Kafka
- xtquant
- MiniQMT
- HTTP
- FastAPI

Domain：

只能：

依赖：

- Python Standard Library
- Shared Kernel
- Domain Interface

---

# 10. Entity Convention

## 10.1 Entity Definition

Entity：

具有：

唯一 Identity。

生命周期。

业务行为。

例如：

```
Order

Trade

Portfolio

Position

Account

Strategy
```

都是：

Entity。

---

## 10.2 Entity Rules

Entity：

必须：

拥有：

唯一 ID。

例如：

```
order_id

trade_id

position_id
```

禁止：

使用：

数据库主键：

作为业务身份。

---

## 10.3 Entity Behavior

Entity：

必须：

拥有：

业务方法。

例如：

```
order.submit()

order.cancel()

order.fill()
```

禁止：

Entity：

只有：

Getter。

Setter。

---

## 10.4 Entity State

Entity：

所有状态：

必须：

由：

State Machine。

驱动。

禁止：

```
order.status = FILLED
```

必须：

```
order.transition(
    OrderStatus.FILLED
)
```

---

# 11. Aggregate Convention

## 11.1 Aggregate Root

每个 Context：

必须：

拥有：

Aggregate Root。

例如：

Trading Context：

```
Order
```

Portfolio Context：

```
Portfolio
```

Risk Context：

```
RiskPolicy
```

---

## 11.2 Aggregate Boundary

Aggregate：

内部对象：

只能：

通过：

Aggregate Root：

访问。

禁止：

```
trade.position.xxx
```

必须：

```
portfolio.add_trade()
```

---

## 11.3 Aggregate Consistency

一个事务：

只能：

修改：

一个 Aggregate。

跨 Aggregate：

必须：

Event。

---

## 11.4 Aggregate Size

Aggregate：

保持：

小。

不要：

一个 Aggregate：

管理：

几十个对象。

---

# 12. Value Object Convention

## 12.1 Definition

Value Object：

没有 Identity。

不可变。

例如：

```
Money

Price

Volume

Commission

Symbol

OrderType
```

---

## 12.2 Immutable

Value Object：

必须：

Immutable。

例如：

```
Money

100

↓

不能：

改成：

200
```

必须：

创建：

新的：

Money。

---

## 12.3 Equality

Value Object：

比较：

Value。

不是：

Identity。

例如：

```
Money(100)

==

Money(100)
```

---

# 13. Domain Service Convention

## 13.1 When to Use

Entity：

无法完成：

业务。

才建立：

Domain Service。

例如：

```
RiskService

PortfolioCalculator

PositionCalculator
```

---

## 13.2 Forbidden

不要：

什么都：

Service。

例如：

```
OrderService

TradeService

PositionService
```

如果：

业务：

属于：

Entity。

应该：

进入：

Entity。

---

# 14. Repository Convention

Repository：

负责：

Aggregate：

持久化。

不是：

SQL。

---

## 14.1 Interface First

例如：

```
OrderRepository
```

定义：

Interface。

实现：

```
SQLAlchemyOrderRepository

MemoryOrderRepository
```

---

## 14.2 Repository Scope

Repository：

只能：

操作：

Aggregate。

禁止：

```
insert_trade()

insert_position()

insert_order()

全部：

放一起。
```

---

## 14.3 Repository Return

Repository：

返回：

Domain Object。

禁止：

返回：

ORM。

例如：

错误：

```
OrderORM
```

正确：

```
Order
```

---

# 15. Factory Convention

Factory：

负责：

复杂对象创建。

例如：

```
OrderFactory

SignalFactory

StrategyFactory
```

---

Factory：

禁止：

业务逻辑。

禁止：

数据库。

禁止：

Broker。

---

# 16. Specification Convention

复杂业务规则：

必须：

Specification。

例如：

```
TradableSpecification

RiskSpecification

MarketOpenSpecification
```

不要：

```
if

if

if

if
```

---

Specification：

可以：

组合。

例如：

```
AND

OR

NOT
```

---

# 17. Domain Event Convention

所有：

Domain：

变化：

必须：

Event。

例如：

```
OrderCreatedEvent

OrderFilledEvent

PositionOpenedEvent

PortfolioChangedEvent
```

---

## 17.1 Event Immutable

Event：

不可修改。

创建后：

只读。

---

## 17.2 Event Naming

统一：

```
Verb + Event
```

例如：

```
OrderCreatedEvent

OrderSubmittedEvent

TradeExecutedEvent

PositionChangedEvent
```

---

## 17.3 Event Publishing

Entity：

产生：

Event。

Application：

负责：

Publish。

Entity：

不要：

知道：

EventBus。

---

# 18. Domain Exception Convention

Domain：

只能：

抛出：

Business Exception。

例如：

```
RiskRejectedException

InvalidOrderException

PositionClosedException
```

禁止：

```
HTTPException

RedisException

DatabaseException
```

---

# 19. Dependency Rule

整个 Domain：

依赖方向：

```
Entity

↓

ValueObject

↓

Specification

↓

Repository Interface

↓

Nothing
```

禁止：

```
Entity

↓

Redis

↓

SQLAlchemy

↓

MiniQMT
```

---

# 20. Code Example

## ❌ Bad Example

```python
class Order:

    def buy(self):

        session.add(self)

        xt.submit()

        logger.info()
```

违反：

- DDD
- Gateway
- Repository
- Infrastructure

---

## ✅ Good Example

```python
class Order(AggregateRoot):

    def submit(self) -> None:

        self.transition(
            OrderStatus.SUBMITTED
        )

        self.add_event(
            OrderSubmittedEvent(
                order_id=self.id
            )
        )
```

Order：

不知道：

数据库。

不知道：

Broker。

不知道：

Redis。

不知道：

EventBus。

只负责：

业务。

---

Part02 End
