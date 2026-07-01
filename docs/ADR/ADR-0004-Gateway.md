# ADR-0004：采用 Gateway Architecture（统一网关架构）
| 属性 | 内容 |
| --- | --- |
| ADR 编号 | ADR-0004 |
| 标题 | Adopt Gateway Architecture |
| 状态 | Accepted |
| 日期 | 2026-06-30 |
| 决策者 | quantiqmt Architecture Team |


---

# 1. Context（背景）
量化交易平台需要与大量外部系统进行交互，例如：

+ MiniQMT
+ CTP
+ Interactive Brokers（IB）
+ Backtest Engine
+ Market Replay
+ PostgreSQL
+ Redis
+ Kafka
+ Prometheus

这些系统：

协议不同。

数据格式不同。

生命周期不同。

异常处理方式不同。

如果业务代码直接依赖这些系统，将导致：

+ 高耦合
+ 无法测试
+ 无法回测
+ 无法替换 Broker
+ 无法扩展新的市场

因此，需要建立统一的 Gateway Architecture。

---

# 2. Problem Statement（问题）
传统交易系统通常采用：

```plain
Strategy

↓

MiniQMT API

↓

Exchange
```

或者：

```plain
Strategy

↓

xtquant

↓

MiniQMT
```

这种设计存在以下问题：

## Broker 耦合
Strategy：

知道：

MiniQMT。

以后：

切换：

CTP。

IB。

所有策略：

全部修改。

---

## 回测无法复用
回测：

需要：

Mock：

MiniQMT。

大量：

if live

if backtest

代码。

---

## Infrastructure 泄漏
Domain：

知道：

Redis。

知道：

SQLAlchemy。

知道：

HTTP。

违反：

Dependency Inversion Principle。

---

## 测试困难
无法：

Mock。

无法：

Fake。

无法：

Unit Test。

---

# 3. Decision（架构决策）
整个系统采用 Gateway Architecture。

所有外部系统：

统一通过 Gateway 接入。

Domain：

只能依赖：

Gateway Interface。

不能依赖：

任何具体实现。

Gateway 的具体实现：

属于：

Infrastructure。

---

# 4. Architecture（架构）
整体结构如下：

```latex
                  Strategy

                      │

        ┌─────────────┴─────────────┐

        ▼                           ▼

Market Gateway              Execution Gateway

        │                           │

        ▼                           ▼

Live Market                 Broker Gateway

Backtest Market                   │

Replay Market                     ▼

                    ┌──────────────┬──────────────┐

                    ▼              ▼              ▼

             MiniQMT Broker   CTP Broker    Backtest Broker
```

整个 Domain：

只能看到：

```plain
MarketGateway

ExecutionGateway
```

不知道：

MiniQMT。

不知道：

CTP。

不知道：

Backtest。

---

# 5. Gateway Responsibilities（职责）
Gateway：

不是：

业务对象。

Gateway：

负责：

系统边界。

主要职责：

+ 协议转换
+ 数据格式转换
+ 异常转换
+ 生命周期管理
+ 连接管理
+ 重试机制
+ 超时处理

Gateway：

禁止：

实现业务规则。

---

# 6. Market Gateway
Market Gateway：

负责：

统一行情入口。

所有行情来源：

统一抽象：

```plain
MarketGateway
```

支持：

```plain
LiveMarketGateway

BacktestMarketGateway

ReplayMarketGateway
```

统一输出：

```plain
TickEvent

BarEvent

SnapshotEvent
```

Strategy：

不知道：

Tick：

来自：

MiniQMT。

Replay。

CSV。

统一：

消费：

Event。

---

# 7. Execution Gateway
Execution Gateway：

负责：

统一执行入口。

OMS：

创建：

Order。

Execution：

负责：

发送：

Order。

Execution：

不知道：

Broker。

Execution：

调用：

```plain
BrokerGateway
```

统一执行。

---

# 8. Broker Gateway
Broker Gateway：

负责：

统一 Broker 接口。

例如：

```plain
MiniQMTBroker

CTPBroker

IBBroker

BacktestBroker
```

所有 Broker：

实现：

统一接口。

例如：

```plain
submit_order()

cancel_order()

query_order()

query_trade()

query_position()

query_account()

subscribe_order()

subscribe_trade()
```

OMS：

无需知道：

Broker 类型。

---

# 9. Dependency Rule（依赖规则）
整个系统：

必须遵守：

```plain
Application

↓

Domain

↓

Gateway Interface

↓

Infrastructure Implementation
```

禁止：

```plain
Domain

↓

MiniQMT
```

禁止：

```plain
Strategy

↓

xtquant
```

禁止：

```plain
Order

↓

SQLAlchemy
```

---

# 10. Gateway Lifecycle（生命周期）
Gateway：

统一生命周期：

```latex
Created

↓

Configured

↓

Connecting

↓

Connected

↓

Running

↓

Reconnecting

↓

Disconnected

↓

Stopped
```

任何 Gateway：

必须实现：

统一生命周期。

---

# 11. Gateway Failure（故障处理）
Gateway：

必须：

负责：

异常隔离。

例如：

Broker：

断线。

Gateway：

自动：

Reconnect。

Strategy：

无需：

感知。

例如：

Redis：

不可用。

Gateway：

降级。

业务：

继续运行。

Gateway：

不得：

导致：

整个系统退出。

---

# 12. Gateway Design Principles（设计原则）
## Principle 1：Domain Isolation
Domain：

不知道：

任何第三方 SDK。

---

## Principle 2：Replaceable
任何 Gateway：

必须：

可替换。

例如：

```plain
MiniQMT

↓

CTP
```

无需修改：

Domain。

---

## Principle 3：Interface First
先定义：

Interface。

再实现：

Gateway。

禁止：

先写：

MiniQMT。

再抽象。

---

## Principle 4：Business Free
Gateway：

不得：

实现：

业务逻辑。

例如：

禁止：

```plain
if price > xx

buy
```

Gateway：

只负责：

通信。

---

## Principle 5：Error Translation
Gateway：

统一：

转换：

第三方异常。

例如：

```plain
MiniQMTError

↓

BrokerDisconnectedException
```

Domain：

不知道：

MiniQMT。

---

# 13. Consequences（影响）
采用 Gateway Architecture 后：

优点：

+ Domain 完全独立
+ Broker 易于替换
+ 回测与实盘统一
+ 易于 Mock
+ 易于测试
+ 易于扩展
+ Infrastructure 可演进
+ 降低第三方 SDK 影响

缺点：

+ 初期需要编写较多接口
+ Gateway 层增加一定复杂度

这些成本可以接受。

---

# 14. Alternatives Considered（备选方案）
## Domain 直接调用 SDK
未采用。

原因：

高耦合。

无法回测。

无法测试。

---

## 每个 Strategy 一个 Broker
未采用。

原因：

重复代码。

无法统一管理。

---

## Repository 直接访问 Broker
未采用。

原因：

Repository：

负责：

持久化。

Broker：

属于：

Execution。

职责不同。

---

# 15. Implementation Constraints（实现约束）
所有外部依赖：

必须：

实现：

Gateway Interface。

不得：

在：

Domain。

Application。

Strategy。

OMS。

Risk。

中：

直接引用：

+ xtquant
+ MiniQMT SDK
+ Redis Client
+ SQLAlchemy Session
+ Kafka Producer

所有第三方 SDK：

只能存在：

Infrastructure。

---

# 16. References
+ Robert C. Martin — Clean Architecture
+ Eric Evans — Domain-Driven Design
+ Martin Fowler — Gateway Pattern
+ Microsoft Architecture Guide
+ Enterprise Integration Patterns

##  17 .Gateway Matrix（网关矩阵）
把所有 Gateway 一次性定义清楚，而不是只有 `MarketGateway` 和 `BrokerGateway`：

| Gateway | 职责 | 典型实现 |
| --- | --- | --- |
| MarketGateway | 行情数据 | Live / Backtest / Replay |
| BrokerGateway | 委托与回报 | MiniQMT / CTP / IB |
| StorageGateway | 数据持久化 | PostgreSQL / SQLite |
| CacheGateway | 缓存 | Redis / Memory |
| EventGateway | 事件传输 | InProcess / Kafka / NATS |
| NotificationGateway | 通知 | Email / Webhook / 企业微信 |
| ClockGateway | 时间来源 | SystemClock / BacktestClock |


这样整个系统所有对外依赖都会遵循同一套设计原则。

---

## 18 .Gateway Selection（运行时装配）
明确系统如何在启动时装配 Gateway：

```plain
Live Mode
    ├── LiveMarketGateway
    ├── MiniQMTBrokerGateway
    └── PostgreSQLStorageGateway

Backtest Mode
    ├── BacktestMarketGateway
    ├── BacktestBrokerGateway
    └── SQLiteStorageGateway

Replay Mode
    ├── ReplayMarketGateway
    ├── BacktestBrokerGateway
    └── PostgreSQLStorageGateway
```

也就是说，**整个系统只在启动阶段决定 Gateway，实现依赖注入；运行期间，Domain 永远不关心具体实现。**

---

## 19.Gateway Contract（统一契约）
规定所有 Gateway 必须满足统一要求：

+  生命周期一致（Created → Connected → Running → Stopped） 
+  支持健康检查（Health Check） 
+  支持重连（Reconnect） 
+  支持超时控制（Timeout） 
+  支持幂等（Idempotency，适用于 BrokerGateway） 
+  支持结构化日志（Structured Logging） 
+  支持 Trace ID 透传 
+  支持指标采集（Metrics） 

这样，未来无论接入 MiniQMT、CTP、IB，还是 Kafka、Redis，**所有 Gateway 的行为都是一致的**。这会让整个 `infrastructure` 层形成一套统一的工程规范，也是很多大型交易平台长期可维护的重要原因。

