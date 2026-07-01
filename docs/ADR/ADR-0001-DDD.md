# ADR-0001：采用 Domain Driven Design（DDD）
| 属性 | 内容 |
| --- | --- |
| ADR 编号 | ADR-0001 |
| 标题 | Adopt Domain Driven Design |
| 状态 | Accepted |
| 日期 | 2026-06-30 |
| 决策者 | quantiqmt Architecture Team |


---

# 1. Context（背景）
quantiqmt 的目标不是一个简单的量化策略脚本，而是一个能够长期演进、支持多个市场、多 Broker、多账户、多策略的企业级量化交易平台。

系统需要同时满足：

+ 回测与实盘共用一套业务逻辑
+ 多策略并行运行
+ 多 Broker 接入
+ Event Driven Architecture
+ 高可维护性
+ 高可测试性
+ 长期演进能力

随着系统不断扩展，订单、账户、持仓、行情、风控等业务对象会持续增长。

如果继续采用传统 Python 项目常见的目录组织方式：

```plain

order.py
trade.py
strategy.py
risk.py

```

最终会出现：

+ 模块之间大量相互依赖
+ Repository 与业务逻辑混杂
+ Service 不断膨胀
+ 修改一个模块影响多个模块
+ 无法支持多人协同开发

因此，需要采用一种能够描述复杂业务领域的软件架构方法。

---

# 2. Problem Statement（问题）
交易系统包含多个天然独立的业务领域：

+ 行情
+ 策略
+ 风控
+ 订单
+ 持仓
+ 账户
+ 回测
+ 监控

这些领域拥有：

+ 不同生命周期
+ 不同状态机
+ 不同数据来源
+ 不同业务规则

如果所有对象都放在一个 Domain 中：

```plain

domain/

order.py
trade.py
position.py
strategy.py
...

```

最终会形成大型 God Object。

系统将难以维护。

---

# 3. Decision（架构决策）
整个系统采用 Domain Driven Design（DDD）。

按照业务领域划分 Bounded Context。

每一个 Context：

+ 独立维护自己的 Entity
+ 独立维护自己的 Domain Service
+ 独立维护自己的 Repository Interface
+ 独立维护自己的 Domain Event
+ 独立维护自己的 Value Object

Context 之间禁止直接共享内部对象。

所有 Context 之间通过 Domain Event 协作。

---

# 4. Bounded Context
系统划分为以下九个 Context：

| Context | 职责 |
| --- | --- |
| Market | 行情管理 |
| Strategy | 策略计算 |
| Trading | OMS、订单、成交 |
| Execution | EMS、Broker 执行 |
| Portfolio | 持仓管理 |
| Account | 账户资金 |
| Risk | 风控 |
| Backtest | 回测 |
| Monitoring | 监控 |


每个 Context 都拥有自己的业务边界。

任何 Context 不允许直接修改其他 Context 的内部状态。

---

# 5. Context 内部结构
所有 Context 必须采用统一目录结构：

```plain

context/

entities/
value_objects/
services/
events/
repositories/
interfaces/
exceptions/

```

示例：

```plain

domain/

trading/

entities/
order.py
trade.py

services/
order_service.py

events/
order_created.py

repositories/
order_repository.py

```

所有 Context 保持一致。

---

# 6. Design Principles（设计原则）
整个系统遵循以下原则：

### 高内聚
一个 Context 只负责一个业务领域。

### 低耦合
Context 之间不能直接调用内部实现。

### Dependency Inversion
依赖接口。

禁止依赖具体实现。

### Contract First

Context 之间只通过公开契约协作：动作用 Command、事实用 Event、读取用 Query。禁止绕过 Application 接口直接修改其他 Context 的聚合，但同进程纯领域计算可以直接调用。详细语义由 [ADR-0006](ADR-0006-Message-Semantics.md) 规定。

### Persistence Ignorance
Domain 不依赖：

+ SQLAlchemy
+ Redis
+ MiniQMT

Domain 不知道数据库。

---

# 7. Architecture Relationship
```plain

Application
↓

Domain
↑
Infrastructure

```

Application：

负责业务流程。

Domain：

负责业务规则。

Infrastructure：

负责技术实现。

---

# 8. Consequences（影响）
采用 DDD 后：

优点：

+ 清晰的业务边界
+ 支持多人开发
+ 支持单元测试
+ Repository 易于 Mock
+ Broker 易于替换
+ 回测与实盘共享业务逻辑
+ 长期维护成本低

缺点：

+ 初期目录复杂
+ 学习成本较高
+ 初期开发速度略慢

这些成本可以接受。

---

# 9. Alternatives Considered（备选方案）
## MVC
未采用。

原因：

MVC 更适合 Web 系统。

不适合复杂交易领域。

---

## 按数据库表划分
例如：

```plain

order/
trade/
position/

```

未采用。

原因：

业务边界不清晰。

Entity 容易互相引用。

---

## 按功能划分
例如：

```plain

service/

controller/

dao/

```

未采用。

原因：

业务逻辑分散。

不符合领域驱动设计。

---

# 10. Implementation Constraints（实现约束）
所有新增业务必须：

属于已有 Context。

不得：

创建：

```plain

utils/order.py

common/trade.py

```

等绕过领域模型的代码。

新增 Context 必须：

新增 ADR。

经过架构评审。

---

# 11. References
+ Eric Evans — Domain-Driven Design
+ Martin Fowler — Patterns of Enterprise Application Architecture
+ Vaughn Vernon — Implementing Domain-Driven Design
+ Microsoft — Domain-Driven Design Guide


